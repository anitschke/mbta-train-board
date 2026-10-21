# AGENTS.md

Welcome! This document provides technical context, architecture guidelines, development conventions, and operational workflows for AI agents and human contributors working on `childrens-museum-franklin-train-board`.

---

## 1. Project Overview & Architecture

`childrens-museum-franklin-train-board` is a CircuitPython application designed to run on the [Adafruit MatrixPortal S3](https://www.adafruit.com/product/5778) driving a 64x32 RGB HUB-75 LED matrix. It is deployed at the [Children's Museum of Franklin](https://www.childrensmuseumfranklin.org/) to track MBTA Franklin commuter rail trains passing by the museum's window.

Its primary functions:
1. **Live Train Arrival Tracking (Default):** Queries the MBTA V3 API (`/schedules` with predictions) for the Franklin line (`place-FB-0275`), calculates arrival time offsets relative to the museum's track position, and displays upcoming arrival times alongside scrolling museum text and an MBTA "T" logo.
2. **Train Passing Animation:** When a train is predicted to arrive (accounting for configurable time warning lead times and standard deviation buffers), plays an animated train sprite (`train.bmp`) in the appropriate direction (inbound or outbound) across the matrix until the train passes.
3. **Interactive Button Trigger:** When either MatrixPortal button (`BUTTON_UP` or `BUTTON_DOWN`) is held, immediately triggers the inbound or outbound train animation.
4. **Resilience & Nightly Maintenance:**
   - Methods wrapped in `_try_method` retry on failures. If repeated failures occur (e.g., persistent network drops), an error screen is displayed and a soft reset (`supervisor.reload()`) is triggered.
   - At 3:00 AM nightly, system time resynchronizes over Adafruit IO NTP, the daily MBTA schedule ID cache is cleared (`train_predictor.clear_cache()`), and garbage collection (`gc.collect()`) runs.

### Hardware Target
- **Board:** Adafruit MatrixPortal S3 (ESP32-S3)
- **Display:** 64x32 RGB LED Matrix (HUB-75, 6mm pitch)
- **Runtime:** CircuitPython 10.0.0 (`adafruit-circuitpython-matrixportal_m4-en_US-10.0.0` or S3 variant)

---

## 2. Directory & Key File Structure

```
├── .github/workflows/ci.yml    # GitHub Actions CI workflow (runs unit tests)
├── main.py                     # Entry point for CircuitPython execution
├── application.py              # Application lifecycle, main loop, retry/recovery, state machine
├── display.py                  # Display driver: arrival times, scrolling text, T-logo, error screen, train sprite
├── buttons.py                  # Hardware button state helpers
├── train_predictor.py          # MBTA V3 API querying, schedule/prediction processing, time offsets
├── train_predictor_test.py     # CPython unit tests for train predictor logic
├── collections_extra.py        # LimitedSizeOrderedSet and LimitedSizeOrderedDict (caching helpers)
├── collections_extra_test.py   # CPython unit tests for collection data structures
├── logging_extra.py            # Logger setup (stdout / StreamHandler & Adafruit IO feed push)
├── time_conversion.py          # Relative time formatting utilities
├── time_conversion_test.py     # CPython unit tests for time conversion
├── settings.toml               # Wi-Fi, Adafruit IO, and MBTA API credentials (git-ignored)
├── install.sh                  # Deployment script to sync project files to mounted CIRCUITPY drive
├── install_circuitpython_lib.sh# Fetches and syncs Adafruit CircuitPython bundle libraries to CIRCUITPY
├── log_tty.sh                  # Shell script to stream and rotate logs from /dev/ttyACM0
├── fonts/                      # BDF bitmap fonts (e.g. 4x6.bdf, 6x10.bdf)
├── background.bmp              # MBTA "T" logo graphic asset
├── train.bmp                   # Sprite sheet for train animation
└── testdata/                   # Test fixtures/data (e.g., recorded MBTA API JSON responses)
```

---

## 3. Critical Conventions & Constraints

### CircuitPython vs. Standard CPython
- **Entrypoint name:** The codebase deliberately uses `main.py` rather than `code.py`. Naming it `code.py` causes a name collision with standard library `code.py` in CPython (which breaks VS Code's test adapter with `ModuleNotFoundError: No module named 'microcontroller'`). **Do not rename `main.py` back to `code.py`**.
- **Dependency Injection for Hardware Libs:** CircuitPython modules (`board`, `displayio`, `adafruit_matrixportal`, `digitalio`, `supervisor`) are generally not importable in standard desktop CPython. To maintain desktop testability, pass hardware/library dependencies into constructors (`ApplicationDependencies`, `TrainPredictorDependencies`, `DisplayDependencies`, `TimeConversionDependencies`, `LoggerDependencies`) rather than instantiating hardware objects inside business logic classes.
- **Resource Constraints & Garbage Collection:** Memory on microcontrollers is constrained. Explicit `gc.collect()` calls are placed after display initialization, API response parsing, and nightly tasks.
- **Display Layering & Label Management:**
  - When rendering layers in `displayio`, order matters: the "T" logo (`background.bmp`) is placed on top with transparent palette entries so text scrolls neatly under it.
  - When no train is available, render a single space (`" "`) rather than an empty string (`""`) to keep the underlying text label allocated and prevent label recreation bugs.
- **File System Writes & Flash Wear:** Avoid logging to the local FAT filesystem (`/`). Local disk writes cause LED flickering due to power/bus contention and wear out the microcontroller's SPI flash. Logs should go to stdout (`StreamHandler`) and Adafruit IO (`AIOHandler`).
- **Synchronous HTTP & Button Polling:** CircuitPython requests on MatrixPortal lack async support; HTTP fetches are timed between full text scroll cycles and train animations. Buttons are active low (`Pull.UP`) and polled synchronously.
- **Daily MBTA Schedule ID Reuse:** MBTA schedule IDs are reused day-to-day. Nightly maintenance must call `train_predictor.clear_cache()` to prevent arrived trains from the previous day poisoning current-day predictions.

---

## 4. Development & Testing Commands

### Running Unit Tests
Unit tests run using standard CPython (tested with Python 3.13+):
```bash
python3 -m unittest discover -p "*_test.py"
```

### Flashing & Deploying to Hardware
1. **Prepare Secrets:** Ensure `settings.toml` exists in the repository root with valid Wi-Fi, Adafruit IO, and MBTA API credentials:
   ```toml
   CIRCUITPY_WIFI_SSID = "your_ssid"
   CIRCUITPY_WIFI_PASSWORD = "your_password"
   ADAFRUIT_AIO_USERNAME = "your_aio_username"
   ADAFRUIT_AIO_KEY = "your_aio_key"
   MBTA_API_KEY = "your_mbta_api_key"
   MBTA_STOP_ID = "place-FB-0275"
   ```
2. **Install CircuitPython Libraries (First-time or Update):**
   Mount the device (default path: `/run/media/anitschk/CIRCUITPY`) and run:
   ```bash
   ./install_circuitpython_lib.sh
   ```
3. **Deploy Code & Assets:**
   Synchronize local scripts, fonts, and assets to the device using:
   ```bash
   ./install.sh
   ```
   *(Note: `install.sh` uses `rsync --inplace` to prevent IO errors on CircuitPython's USB mass storage emulation).*

### Debugging & Serial Monitoring
- **Interactive REPL & Serial Console:**
  ```bash
  screen /dev/ttyACM0
  ```
  *(Check `/dev/ttyACM*` if reconnected under an alternate device index).*
- **Continuous Logging to File:**
  ```bash
  ./log_tty.sh
  ```

---

## 5. Development Guidelines & Change Protocol

When modifying or extending this codebase, adhere to the following rules:

1. **Keep Unit Tests Updated & Passing:**
   - Always run existing unit tests with `python3 -m unittest discover -p "*_test.py"` to ensure no regressions.
   - Any new or modified business logic, time math, collections, or prediction logic must be accompanied by corresponding unit tests (named `*_test.py`).
   - Maintain the dependency injection pattern so new logic can be tested in standard CPython without importing hardware packages (`board`, `displayio`, `supervisor`, etc.).

2. **Synchronize Documentation (`AGENTS.md` & `README.md`):**
   - **`AGENTS.md`**: Whenever architecture, coding conventions, deployment procedures, script usages, or critical constraints change, update this document to keep agent and developer context accurate.
   - **`README.md`**: Whenever user-facing features, hardware configurations, wiring, secrets, setup instructions, or dependencies change, update `README.md` accordingly.

3. **Synchronize `install.sh` when Adding/Removing Files:**
   - Any runtime Python script, graphic asset, or resource file that is added or removed from the project **must be added or removed in `install.sh`** (the `rsync` file list). If this is not done, the file will not be copied to the CircuitPython board during deployment.
   - Also update the directory layout tree in `AGENTS.md` to reflect the new or removed file.
