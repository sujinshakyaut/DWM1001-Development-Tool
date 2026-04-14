# DWM1001-Dev

A desktop GUI application for configuring and monitoring Decawave DWM1001-DEV UWB modules over Bluetooth Low Energy.

## Table of Contents

- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [API](#api)
- [Contributing](#contributing)
- [License](#license)

## Background

The DWM1001-DEV module exposes its configuration over BLE but has no official desktop tool. This project provides a Tkinter GUI backed by a local FastAPI server to bridge that gap.

Tkinter and `bleak` (the BLE library) cannot share the same thread: Tkinter blocks the main thread with `root.mainloop()` while bleak requires a dedicated asyncio event loop. Running FastAPI and uvicorn in a background daemon thread isolates the two runtimes cleanly. The GUI talks to the BLE layer exclusively over HTTP on `127.0.0.1:8000`, which also means every BLE operation is testable via Swagger UI without the GUI.

Requires Python 3.10+ and Windows 10/11 (WinRT BLE backend).

## Install

```bash
pip install -r requirements.txt
```

## Usage

Start the application:

```bash
python main.py
```

This starts the FastAPI server on `127.0.0.1:8000` and launches the GUI. Four tabs are available:

- **Scan & Connect** - discover nearby DWM1001 devices and connect over BLE
- **Device Info** - read label, role, operating mode, and PAN ID
- **Configure** - write PAN ID, operating mode, and anchor position
- **Location Stream** - live 2D map, anchor distances, and CSV export

To run the backend alone and browse the interactive API docs:

```bash
uvicorn ble_api:app --reload
```

Then open `http://localhost:8000/docs`.

## API

The FastAPI backend exposes the following endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/status` | Connection status and device address |
| `GET` | `/scan` | Scan for nearby BLE devices |
| `POST` | `/connect` | Connect to a device by address |
| `POST` | `/disconnect` | Disconnect the active device |
| `GET` | `/info` | Read label, role, opmode, and PAN ID |
| `POST` | `/net-id` | Write PAN ID |
| `POST` | `/opmode` | Write operating mode (role, UWB mode, initiator, location engine) |
| `POST` | `/anchor-position` | Set anchor position (x, y, z, quality) |
| `POST` | `/location/start` | Begin BLE location notification stream |
| `POST` | `/location/stop` | Stop the stream |
| `GET` | `/location/poll` | Drain buffered location frames |

Writing the operating mode causes the device to reset and disconnect. This is expected and handled silently.

## Contributing

Open an issue or pull request on [GitHub](https://github.com/sujinshakyaut/DWM1001-Dev). For questions about the BLE protocol, refer to the Decawave DWM1001 System Overview documentation.

## License

MIT
