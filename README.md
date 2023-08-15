
# StockWatcher

## Overview
StockWatcher is an automated tool that monitors stocks prices. Leveraging Google Apps Script and Python, it allows users to view price fluctuations over specified days, providing a straightforward approach to tracking investment trends.

## Installation
Follow these steps to set up the environment:
1. Make sure Python 3.x is installed.
2. Install required libraries: `pip install yfinance pandas requests`
3. Create a Google Apps Script project and deploy the code.
4. Set the GAS endpoint URL in the environment variables.

## Usage
1. Run the script with specified stock codes: `python3 stock_post.py 2914.T,1419.T`
2. Run the script without arguments for processing all stocks: `python3 stock_post.py`

## Structure
- **Google Apps Script**: Manages the spreadsheet, imports and formats stock price data.
- **Python**: Fetches stock price data using yfinance, sends to GAS in JSON format.

## Contribution
Contributions to the project are welcome! Feel free to report bugs, suggest features, or make a pull request.

## License
This project is licensed under the Apache License 2.0. For more details, see the [LICENSE](LICENSE) file.

## Contact
If you encounter any issues or need support, please [contact us](mailto:your-email@example.com).
