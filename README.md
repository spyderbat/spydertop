# Spydertop Tool

Spydertop, is a tool that provides htop-like functionality for any point in time, on any of your Spyderbat sources. This allows a view of system processes and statuses at points in the past, for any of the sources in your Spyderbat ORG.

## Installation/Quick Start

Spydertop uses the Spyderbat APIs, so it must have access to a valid API key, usually stored in a configuration file, as shown below. API keys can be obtained from the API keys page under your Spyderbat account.

```yaml
# File: ~/.sbapi/config.yaml
default:
    api_key: API_KEY
    org:     DEFAULT_ORG_ID    # optional
    source:  DEFAULT_SOURCE_ID # optional
    api_url: apr.prod.spyderbat.com # optional
```

### Quick Install

Run [install.sh](install.sh). This will install spydertop using the `pip` command in the current Python environment.

On your first run of `spydertop`, it will guide you through setting up a configuration if you do not have one already.

### Manual

Spydertop requires python with setup-tools to install, and the Python version of the Spyderbat API. This can be installed from the [GitHub page](https://github.com/spyderbat/api_examples/tree/main/python) or using the following commands:

```sh
git clone https://github.com/spyderbat/api_examples.git
cd api_examples/python
pip install .
```

The install command can then be run in this directory:

```sh
pip install .
```

On your first run of `spydertop`, it will guide you through setting up a configuration if you do not have one already. If you prefer to set it up yourself, your organization id can be found in the url for the dashboard, and many other pages:

```url
https://api.prod.spyderbat.com/app/org/{ORG_ID_HERE}/dashboard
```

Similarly, the source id can be located in the url of an investigation, or by enabling the id column in the sources list.

## Usage

Spydertop is called with options specifying the source to pull from and how that data is collected, and a timestamp. Records will be loaded from the specified source around the time, and an htop-like view will start at the exact requested time. The relative time selection bar at the bottom can be used to move forward and backward in time, and arrow keys, tab key, or mouse used to navigate the interface. More usage information is available on the help page (`h` or `<F1>`).

As this tool emulates much of HTOP's functionality, more information is also available on the HTOP man page.

## Examples

```sh
spydertop --help # print usage information

# starts spydertop with the specified source
# at a point in time 5 days ago
spydertop -g ORGUID --s SOURCEUID -- -5d

# full example
spydertop \
        --organization ORGUID \
        --source SOURCEUID \
        --duration 3m \
        --input cached_input_records.json.gz \
        --output file_to_save_to.json.gz \
        --log-level WARN \
        -- 1654303663.600901
```
