# Audio Query Generator

This tool generates audio queries using the ESPnet library and a provided model.

## Prerequisites

- Python 3.10
- Virtual Environment (venv)

## Installation

1. Clone the repository:

    ```bash
    git clone https://github.com/samiabat/text2speech
    cd text2speech
    ```

2. Create and activate a virtual environment:

    ```bash
    python3.10 -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3. Install the required dependencies:

    ```bash
    pip install -r requirements.txt
    ```

    Note: Ensure that you are using Python 3.10, as some libraries like pyopenjtalk may not work with Python 3.11.

4. Download the ESPnet model and add the `config.yaml` file inside the `model` folder.

## Usage

Run the following command to generate audio queries:

```bash
python audioQueryGenerator.py
