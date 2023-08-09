# Spydertop

Spydertop is a tool that provides htop-like functionality for any point in time, on any of your Spyderbat-enabled machines. Utilizing Spyderbat’s kernel-level system monitoring and public APIs, Spydertop allows analysts to look into system anomalies days or even months after they occur.

## Demo:

![A demo of Spydertop](https://github.com/spyderbat/spydertop/blob/main/assets/demo.gif)

## Quick Start

If you would like to try spydertop without installing it first, you can run the [docker image](https://hub.docker.com/r/spyderbat/spydertop). Example data from the `examples` directory is included in the docker image.

```sh
# to run without arguments
docker run -it spyderbat/spydertop

# to run on an example
docker run -it spyderbat/spydertop -i examples/minikube-sock-shop.json.gz

# to persist settings, or to use a pre-configured Spyderbat API
docker run -it -v $HOME/.config/spydertop:/root/.config/spydertop spyderbat/spydertop [ARGS]

# to run docker with the host's timezone settings
docker run -it -v /etc/localtime:/etc/localtime spyderbat/spydertop [ARGS]
```

You can also download the bundled executable from the [releases page](https://github.com/spyderbat/spydertop/releases), which includes everything necessary to run spydertop, including a compatible python version!

## Installation

Spydertop can be installed from [PyPi](https://pypi.org/project/spydertop/) with pip:

```sh
pip install spydertop
```

If you prefer a manual install, you can download and install the appropriate wheel file or bundled executable (`spydertop-bundled-XXX`) from the [releases page](https://github.com/spyderbat/spydertop/releases).

To install from source, clone this repository and run this command inside:

```sh
# note: requires setuptools >= 45
pip install .
# pip install . -e # for editable install
```

On your first run of `spydertop`, it will guide you through setting up a basic configuration if you do not have one already. If you prefer to set it up yourself, see [Configuration](#configuration).

## Usage

Spydertop is called with options specifying the machine to pull from and how that data is collected, and a timestamp. Records will be loaded from the specified machine around that time, and an htop-like view will start at the exact requested time. The relative time selection bar at the bottom or bracket keys (`[` or `]`) can be used to move forward and backward in time, and the arrow keys, tab key, or mouse can be used to navigate the interface. More usage information is available on the help page (`h` or `<F1>`).

As this tool emulates much of HTOP's functionality, more information is also available on the HTOP man page.

## Examples

```sh
spydertop --help # print usage information

# starts spydertop with the specified machine
# at a point in time 5 days ago
spydertop load -g ORGUID -m MACHINEUID -- -5d

# full example
spydertop load \
        --organization ORGUID \
        --machine MACHINEUID \
        --duration 3m \
        --input cached_input_records.json.gz \
        --output file_to_save_to.json.gz \
        -- 1654303663.600901
```

## Configuration

The current configuration, and it's location on disk, can be viewed with

```bash
spydertop config get
```

Spydertop uses the Spyderbat APIs, so it must have access to a valid API key. API keys can be obtained from the API keys page under your Spyderbat account, and configured in spydertop using the `spydertop config set-secret` command:

```bash
spydertop config set-secret mysecret --api-key $(cat ./apikey.txt)
```

When using the `load` command, spydertop uses a *context* to determine how to load data. By default, you will have to specify the organization and source every time you start spydertop. However, you can update or create a new context to configure default values:

```bash
spydertop config set-context mycontext --secret mysecret --organization ORG_ID --source SOURCE_ID
```

Your organization id can be found in the url for the dashboard, and many other pages. Similarly, the machine id can be located in the url of an investigation, or by enabling the id column in the sources list.

```url
https://api.spyderbat.com/app/org/{ORG_ID_HERE}/dashboard
```

After creating a context, you can enable it with:

```bash
spydertop config use-context mycontext
```

## Development

For development, Spydertop can be installed with the `--editable` flag in `pip`. Spydertop works well inside of a Python virtual environment, so using one is recommended.

```sh
# in the spydertop repository:

# setup development environment
python -m venv .venv
source .venv/bin/activate

# install spydertop for development
pip install --editable .
```

In the virtual environment, after editing and saving a file, the `spydertop` command will automatically be updated.

See the [Project Structure](https://github.com/spyderbat/spydertop/blob/main/structure.md) for a walk through of Spydertop's code base.

## Debugging

If you are using VSCode, `launch.json` is configured to run Spydertop with the python extension's debugger. This runs the module as a python file instead of through the command line, so command line arguments can be added in `__init__.py`.
