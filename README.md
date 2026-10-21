# mbta-train-board

This project is a train arrival and departure board that displays upcoming MBTA commuter rail (or subway) times on an LED matrix display.

This repository is a fork of [childrens-museum-franklin-train-board](https://github.com/anitschke/childrens-museum-franklin-train-board). While the original project was built specifically for the [Children's Museum of Franklin](https://www.childrensmuseumfranklin.org/) to predict when trains would pass by a museum window located between stations, this fork is intended for general use—such as for a family member living close to an MBTA station who wants to see when the T is arriving at or leaving the station near their house. Instead of calculating custom track offsets for a location between stations, this version displays station arrival and departure times directly from the MBTA API for any configured station.

![train board gif](./train-board.gif)

## Hardware

Adafruit makes it super easy to create an internet connected LED board like this. They sell a ESP32-S3 based board that integrates with HUB-75 based LED boards. Plug it in, write some python code, and just move it onto the board as if it was a USB drive.
* [Adafruit Matrix Portal S3 CircuitPython Powered Internet Display](https://www.adafruit.com/product/5778)
* [64x32 RGB LED Matrix - 6mm pitch](https://www.adafruit.com/product/2276)
* [TAP Plastics Chemcast Black LED Plastic Sheets](https://www.tapplastics.com/product/plastics/cut_to_size_plastic/black_led_sheet/668) - for on top of the LED board
* [Clear Adhesive Squares](https://www.adafruit.com/product/4813) - For attaching the acrylic sheet on top of the LEDs

## Maxtrix Portal Setup

### Flash with CircuitPython

To put the MatrixPortal S3 into bootloader mode so that the `MATRXS3BOOT` drive appears:
1. **Use a data-capable USB cable:** Make sure you are using a real data USB cable and not a charge-only cable. If you are having issues with the process or want to test if you have the right cable, plug in the board and check if the serial device appears:
   ```sh
   ls /dev/ttyACM*
   ```
   If `/dev/ttyACM0` (or similar) shows up, your cable supports data.
2. **Enter UF2 Bootloader mode:** Double-click the physical **Reset** button on the board.
   * You might not get the timing correct the first time—you may need to try the double-click a little faster or slower.
   * When successful, the onboard NeoPixel status LED will turn **green**, and the `MATRXS3BOOT` drive will appear on your computer.
   * If you have any issues, refer to the [Adafruit MatrixPortal S3 Install CircuitPython instructions](https://learn.adafruit.com/adafruit-matrixportal-s3/install-circuitpython).
3. **Install CircuitPython:**
   * You can install it using the web installer or by copying the `.uf2` file directly:
     * https://circuitpython.org/board/adafruit_matrixportal_s3/
     * "Open Installer"
     * "Install CircuitPython 10.0.0 UF2 Only" (or drag and drop the `.uf2` file onto the `MATRXS3BOOT` drive)
     * Continue following install instructions

Currently using `adafruit-circuitpython-matrixportal_s3-en_US-10.3.1`

### Install Adafruit Library

After setting up CircuitPython we need to install the Adafruit python libraries onto the device. This can be done by running the `install_circuitpython_lib.sh` script. This script installs EVERYTHING from that python bundle. There is a lot more than we need in that lib, but it is only 1MB so it isn't too bad to just include it all. At one pint I set up something to reduce the size and only install what I needed but the way I was doing it seemed to be fragile and I now that I am not logging to the file system I didn't need the extra space so decided to just get rid of that code. See [12639a7](https://github.com/anitschke/childrens-museum-franklin-train-board/commit/12639a794d5604a41d5e1b3bb21851ef8ebe4f4a).

### `settings.toml`

A `settings.toml` must be created inside this directory containing secrets and API keys. It will be copied over to the device when `install.sh` is run in the next step.

* `CIRCUITPY_WIFI_SSID` and `CIRCUITPY_WIFI_PASSWORD` need to contain the wifi SSID and password so the board can connect to wifi
* `CIRCUITPY_WEB_API_PORT` and `CIRCUITPY_WEB_API_PASSWORD` may be set to enable access to the board over wifi, this is generally not recommended for security reasons.
* `ADAFRUIT_AIO_USERNAME` and `ADAFRUIT_AIO_KEY` are required so it can push logs to the adafruit.io log feed and connect to the adafruit.io NTP time server so it can fetch the current time. A free account can be created at io.adafruit.com .
* `MBTA_API_KEY` a free MBTA API key is required to avoid rate limiting issues and to ensure version compatibility of the API. See https://api-v3.mbta.com/ .  

```toml
CIRCUITPY_WIFI_SSID = "REDACTED"
CIRCUITPY_WIFI_PASSWORD = "REDACTED"

ADAFRUIT_AIO_USERNAME = "REDACTED"
ADAFRUIT_AIO_KEY      = "REDACTED"

MBTA_API_KEY = "REDACTED"
```
### Install the program

Run `install.sh` to install all of software and dependencies like the sprite sheet for the animation of the train onto the board.


## Notes

### Request a train

You can request that the train animation can play but holding down either the up or down buttons on the board when right when then "Children's Museum of Franklin" scrolling text disappears.

### Running tests

Unit tests can be run with Python by running the following at the root of the repository. Currently I am using Python 3.13.7 on Linux for testing.

```sh
python -m unittest discover -p "*_test.py"
```

### Logs

Logs for the board are pushed to [adafruit.io](https://io.adafruit.com/anitschke/feeds/cmf-train-board-logging).

### Debugging

You can connect to the board and view logs / get into the Python REPL shell using:

```
screen /dev/ttyACM0
```

* Note that sometimes the device name has a different digit after disconnecting / reconnecting (ex `/dev/ttyACM1`).

### Implementation complexity

The [Adafruit Matrix Portal library](https://github.com/adafruit/Adafruit_CircuitPython_MatrixPortal) is setup to make this sort of LED board **very** easy if all you want to do is fetch some data from an API and display it on the board. An early prototype in the original project used this much simpler approach provided by the library: you give the library a URL to query and a function to post-process the data, and it pipes that into text fields and automatically updates. That implementation can be found in the old commit [42d4df9](https://github.com/anitschke/childrens-museum-franklin-train-board/blob/42d4df91104091cb4706397605a01e57b116b2f3/code.py). 

The implementation in this repository is more structured than that first prototype for a couple of reasons:
* It includes an animated train sprite and scrolling text, which did not fit cleanly into the library's default text update loop.
* It uses dependency injection and modular components so the prediction and display logic can be unit-tested under standard CPython without hardware libraries.

In the original children's museum project, additional complexity was also needed to calculate custom arrival time offsets for trains passing by a track location between stations. For this board, that offset complexity does not apply because we can directly trust the MBTA API's station arrival and departure times.

If you are building a basic board from scratch and only need simple periodic text updates, starting with the simpler approach in commit [42d4df9](https://github.com/anitschke/childrens-museum-franklin-train-board/blob/42d4df91104091cb4706397605a01e57b116b2f3/code.py) is a great baseline.

### Computing arrival time offsets

In the upstream [childrens-museum-franklin-train-board](https://github.com/anitschke/childrens-museum-franklin-train-board) project, the MBTA API could not directly provide arrival times for the museum because the museum was located down the track from Franklin station rather than at a station. That required recording empirical passing times versus predicted times and calculating time offsets (see the [historical data analysis repo](https://github.com/anitschke/childrens-museum-franklin-train-board-data-analysis)).

For this board, computing arrival time offsets is not necessary: because the display is intended for seeing when trains arrive at or leave a station, we can directly trust and display the MBTA V3 API's arrival and departure predictions for the station.

### Train sprite

I made a simple script using ImageMagick to help build a sprite sheet of a train animation to play when the train is about to pass by. The script for building this sprite sheet can be found in this GitHub Repo: https://github.com/anitschke/childrens-museum-franklin-train-board-train-sprite .

### Testing

### dependency injection

Rather than directly import Adafruit Python libraries many of the classes require that dependencies are passed into class contractors. This is primally to support testing. By avoiding directly import Adafruit Python libraries it allows for running tests with normal CPython by passing in mocks or normal Python versions of the classes. 

### `main.py` vs `code.py`

Most circuit python codebases seem to use `code.py` for the main entrypoint file, however circuit python also accept `main.py` as the main entrypoint file. We use `main.py` because VSCode test plugin hits the following error if we attempt to run tests and `code.py` exists. So we will just work around this and name the entry point file `main.py` instead.

```
Traceback (most recent call last):
  File "/home/anitschk/.vscode/extensions/ms-python.python-2025.16.0-linux-x64/python_files/unittestadapter/execution.py", line 24, in <module>
    from django_handler import django_execution_runner  # noqa: E402
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/anitschk/.vscode/extensions/ms-python.python-2025.16.0-linux-x64/python_files/unittestadapter/django_handler.py", line 15, in <module>
    from pvsc_utils import (  # noqa: E402
        VSCodeUnittestError,
    )
  File "/home/anitschk/.vscode/extensions/ms-python.python-2025.16.0-linux-x64/python_files/unittestadapter/pvsc_utils.py", line 6, in <module>
    import doctest
  File "/usr/lib/python3.13/doctest.py", line 101, in <module>
    import pdb
  File "/usr/lib/python3.13/pdb.py", line 77, in <module>
    import code
  File "/home/anitschk/sandbox/childrens-museum-franklin-train-board/code.py", line 4, in <module>
    import microcontroller
ModuleNotFoundError: No module named 'microcontroller'
Finished running tests!
```

### Logging to filesystem

At one point I set this up logging to the file system, see [12639a7](https://github.com/anitschke/childrens-museum-franklin-train-board/commit/12639a794d5604a41d5e1b3bb21851ef8ebe4f4a) but it had issues where logging to the filesystem leads to the LEDs flashing while writing to the file system. I am not sure why, I thought it might be a larger power draw to write to flash and used a better USB power supply but it still flashed. So IDK. I am also a little worried about wearing down the flash storage ( https://stackoverflow.com/questions/45982155/can-a-high-number-of-read-write-deteriorate-the-flash-itself ). It also adds a lot of extra complexity to the code so I reverted that change.

### Thanks to the MBTA

Thanks to the MBTA for your [excellent API documentation for the V3 API](https://www.mbta.com/developers/v3-api), it made this project a lot easier.

### Inspiration

I want to thank Enrique Gamboa for his [Medium article](https://jegamboafuentes.medium.com/i-created-my-own-subway-arrival-board-with-real-time-data-to-dont-miss-my-train-anymore-28bfded312c0) and [GitHub repo](https://github.com/jegamboafuentes/Train_schedule_board) for a very similar train arrival time board that also used the MBTA API. They served as a major form of inspiration when I was working on this project.

## References

* Supporting repos for this project:
  * Train animation sprites - https://github.com/anitschke/childrens-museum-franklin-train-board-train-sprite
  * Arrival time data analysis - https://github.com/anitschke/childrens-museum-franklin-train-board-data-analysis 
* Other train boards:
  * Enrique Gamboa's Medium article - https://jegamboafuentes.medium.com/i-created-my-own-subway-arrival-board-with-real-time-data-to-dont-miss-my-train-anymore-28bfded312c0
  * Enrique Gamboa's GitHub Repo - https://github.com/jegamboafuentes/Train_schedule_board
  * NYC MTA Train Arrival Board - https://github.com/alejandrorascovan/mta-portal
* MBTA API Documentation - https://www.mbta.com/developers/v3-api
* Matrix Portal CircuitPython Documentation - https://docs.circuitpython.org/projects/matrixportal/en/latest/
* Matrix Portal Guide - https://learn.adafruit.com/adafruit-matrixportal-s3




