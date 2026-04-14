import asyncio
import struct
from typing import Literal

from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field

OP_MODE_UUID       = "3f0afd88-7770-46b0-b5e7-9fc099598964"
NET_ID_UUID        = "80f9d8bc-3bff-45bb-a181-2d6a37991208"
LABEL_UUID         = "00002a00-0000-1000-8000-00805f9b34fb"
POSITION_UUID      = "f0f26c9b-2c8c-49ac-ab60-fe03def1b40c"
LOCATION_UUID      = "003bbdf2-c634-4b3d-ab56-7ec889b89a37"
LOCATION_MODE_UUID = "a02b947e-df97-4516-996a-1882521e0ead"

_client: BleakClient | None = None
_client_address: str = ""
_location_task: asyncio.Task | None = None
_location_queue: asyncio.Queue = asyncio.Queue()
_scanned_devices: dict[str, BLEDevice] = {}

async def read_label(client: BleakClient) -> str:
    raw = await client.read_gatt_char(LABEL_UUID)
    return raw.decode("utf-8", errors="ignore").strip()


async def read_opmode(client: BleakClient) -> tuple[str, str, str]:
    raw = await client.read_gatt_char(OP_MODE_UUID)
    byte1 = raw[0]
    byte2 = raw[1]
    role      = "Anchor" if (byte1 & 0x80) else "Tag"
    initiator = "Yes"    if (byte2 & 0x80) else "No"
    return role, initiator, raw.hex()


async def read_net_id(client: BleakClient) -> int:
    raw = await client.read_gatt_char(NET_ID_UUID)
    if len(raw) < 2:
        return 0
    return struct.unpack("<H", raw[:2])[0]


async def write_net_id(client: BleakClient, pan_id: int) -> None:
    raw = struct.pack("<H", pan_id)
    await client.write_gatt_char(NET_ID_UUID, raw, response=False)


async def write_opmode(
    client: BleakClient,
    role: str,
    uwb_mode: str,
    initiator: bool = False,
    location_engine: bool = True,
) -> None:
    current = await client.read_gatt_char(OP_MODE_UUID)
    byte1 = current[0]
    byte2 = current[1]

    if role == "anchor":
        byte1 |= (1 << 7)
    else:
        byte1 &= ~(1 << 7)

    byte1 &= ~(0x03 << 5)
    if uwb_mode == "passive":
        byte1 |= (1 << 5)
    elif uwb_mode == "active":
        byte1 |= (2 << 5)

    if initiator:
        byte2 |= (1 << 7)
    else:
        byte2 &= ~(1 << 7)

    if location_engine:
        byte2 |= (1 << 5)
    else:
        byte2 &= ~(1 << 5)

    raw = bytes([byte1, byte2])
    try:
        await client.write_gatt_char(OP_MODE_UUID, raw, response=True)
    except Exception:
        pass


class ConnectRequest(BaseModel):
    address: str

class WriteNetIdRequest(BaseModel):
    pan_id: int

class WriteOpmodeRequest(BaseModel):
    role: Literal["tag", "anchor"]
    uwb_mode: Literal["active", "passive", "off"]
    initiator: bool = False
    location_engine: bool = True

class SetAnchorPositionRequest(BaseModel):
    x: int
    y: int
    z: int
    quality: int = Field(ge=0, le=100)

class StartLocationRequest(BaseModel):
    duration: int = 30


class DeviceInfo(BaseModel):
    address: str
    name: str

class ScanResponse(BaseModel):
    devices: list[DeviceInfo]

class ConnectResponse(BaseModel):
    connected: bool
    address: str

class ReadInfoResponse(BaseModel):
    label: str
    role: str
    initiator: str
    opmode_hex: str
    pan_id_hex: str
    pan_id_int: int

class WriteResponse(BaseModel):
    success: bool
    message: str

class PositionData(BaseModel):
    x: int
    y: int
    z: int
    quality: int

class AnchorDistance(BaseModel):
    node_id_hex: str
    distance_mm: int
    quality: int

class LocationFrame(BaseModel):
    msg_type: int
    position: PositionData | None = None
    anchors: list[AnchorDistance] = []

class LocationPollResponse(BaseModel):
    frames: list[LocationFrame]
    streaming: bool


app = FastAPI(title="DWM1001-BLE API")


async def require_client() -> BleakClient:
    if _client is None or not _client.is_connected:
        raise HTTPException(status_code=409, detail="Not connected to any device")
    return _client


@app.get("/status", response_model=ConnectResponse)
async def get_status():
    return ConnectResponse(
        connected=(_client is not None and _client.is_connected),
        address=_client_address,
    )


@app.get("/scan", response_model=ScanResponse)
async def scan_devices():
    global _scanned_devices
    try:
        found = await asyncio.wait_for(BleakScanner.discover(), timeout=10)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="BLE scan timed out")
    _scanned_devices = {d.address: d for d in found}
    devices = [
        DeviceInfo(address=d.address, name=d.name or "Unknown")
        for d in found
    ]
    return ScanResponse(devices=devices)


def _on_disconnect(_: BleakClient) -> None:
    global _client, _client_address
    _client = None
    _client_address = ""


@app.post("/connect", response_model=ConnectResponse)
async def connect_device(body: ConnectRequest):
    global _client, _client_address
    if _client is not None and _client.is_connected:
        await _client.disconnect()
    ble_target: BLEDevice | str = _scanned_devices.get(body.address, body.address)
    try:
        _client = BleakClient(ble_target, disconnected_callback=_on_disconnect)
        await _client.connect()
    except Exception as e:
        _client = None
        _client_address = ""
        raise HTTPException(status_code=500, detail=f"Connection failed: {e}")
    _client_address = body.address
    return ConnectResponse(connected=True, address=_client_address)


@app.post("/disconnect", response_model=WriteResponse)
async def disconnect_device():
    global _client, _client_address
    if _client is not None:
        try:
            await _client.disconnect()
        except Exception:
            pass
        _client = None
        _client_address = ""
    return WriteResponse(success=True, message="Disconnected")


@app.get("/info", response_model=ReadInfoResponse)
async def read_info(client: BleakClient = Depends(require_client)):
    label = await read_label(client)
    role, initiator, opmode_hex = await read_opmode(client)
    pan_id = await read_net_id(client)
    return ReadInfoResponse(
        label=label,
        role=role,
        initiator=initiator,
        opmode_hex=opmode_hex,
        pan_id_hex=f"0x{pan_id:04X}",
        pan_id_int=pan_id,
    )


@app.post("/net-id", response_model=WriteResponse)
async def set_net_id(body: WriteNetIdRequest, client: BleakClient = Depends(require_client)):
    await write_net_id(client, body.pan_id)
    return WriteResponse(success=True, message=f"PAN ID set to 0x{body.pan_id:04X}")


@app.post("/opmode", response_model=WriteResponse)
async def set_opmode(body: WriteOpmodeRequest, client: BleakClient = Depends(require_client)):
    await write_opmode(client, body.role, body.uwb_mode, body.initiator, body.location_engine)
    return WriteResponse(success=True, message="OpMode written (device may reset)")


@app.post("/anchor-position", response_model=WriteResponse)
async def set_anchor_position(
    body: SetAnchorPositionRequest,
    client: BleakClient = Depends(require_client),
):
    raw = struct.pack("<iiiB", body.x, body.y, body.z, body.quality)
    await client.write_gatt_char(POSITION_UUID, raw, response=False)
    return WriteResponse(
        success=True,
        message=f"Position set: x={body.x} y={body.y} z={body.z} quality={body.quality}",
    )


def _parse_location_frame(data: bytes) -> LocationFrame | None:
    if len(data) < 1:
        return None
    msg_type = data[0]

    if msg_type == 0:
        if len(data) < 14:
            return None
        x, y, z, quality = struct.unpack("<iiiB", data[1:14])
        return LocationFrame(
            msg_type=0,
            position=PositionData(x=x, y=y, z=z, quality=quality),
        )

    elif msg_type == 1:
        if len(data) < 2:
            return None
        count = data[1]
        anchors = []
        offset = 2
        for _ in range(count):
            if offset + 7 > len(data):
                break
            node_id  = struct.unpack("<H", data[offset:offset+2])[0]
            distance = struct.unpack("<I", data[offset+2:offset+6])[0]
            quality  = data[offset+6]
            anchors.append(AnchorDistance(
                node_id_hex=f"0x{node_id:04X}",
                distance_mm=distance,
                quality=quality,
            ))
            offset += 7
        return LocationFrame(msg_type=1, anchors=anchors)

    elif msg_type == 2:
        if len(data) < 15:
            return None
        x, y, z, quality = struct.unpack("<iiiB", data[1:14])
        count = data[14]
        anchors = []
        offset = 15
        for _ in range(count):
            if offset + 7 > len(data):
                break
            node_id  = struct.unpack("<H", data[offset:offset+2])[0]
            distance = struct.unpack("<I", data[offset+2:offset+6])[0]
            q        = data[offset+6]
            anchors.append(AnchorDistance(
                node_id_hex=f"0x{node_id:04X}",
                distance_mm=distance,
                quality=q,
            ))
            offset += 7
        return LocationFrame(
            msg_type=2,
            position=PositionData(x=x, y=y, z=z, quality=quality),
            anchors=anchors,
        )

    return None


async def _run_location_stream(client: BleakClient, duration: int) -> None:
    await client.write_gatt_char(LOCATION_MODE_UUID, bytes([2]), response=False)

    def on_notification(sender, data):
        try:
            frame = _parse_location_frame(bytes(data))
            if frame is not None:
                _location_queue.put_nowait(frame)
        except Exception:
            pass

    await client.start_notify(LOCATION_UUID, on_notification)
    await asyncio.sleep(duration)
    await client.stop_notify(LOCATION_UUID)


@app.post("/location/start", response_model=WriteResponse)
async def location_start(
    body: StartLocationRequest,
    client: BleakClient = Depends(require_client),
):
    global _location_task
    if _location_task is not None and not _location_task.done():
        raise HTTPException(status_code=400, detail="Already streaming")
    _location_task = asyncio.create_task(_run_location_stream(client, body.duration))
    return WriteResponse(success=True, message=f"Streaming started for {body.duration}s")


@app.post("/location/stop", response_model=WriteResponse)
async def location_stop():
    global _location_task
    if _location_task is not None and not _location_task.done():
        _location_task.cancel()
        try:
            await _location_task
        except asyncio.CancelledError:
            pass
        if _client is not None and _client.is_connected:
            try:
                await _client.stop_notify(LOCATION_UUID)
            except Exception:
                pass
    _location_task = None
    return WriteResponse(success=True, message="Streaming stopped")


@app.get("/location/poll", response_model=LocationPollResponse)
async def location_poll():
    frames = []
    while not _location_queue.empty():
        frames.append(_location_queue.get_nowait())
    streaming = _location_task is not None and not _location_task.done()
    return LocationPollResponse(frames=frames, streaming=streaming)
