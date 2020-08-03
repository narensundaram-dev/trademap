Setup:
    - Install chrome-driver(for your chrome version) from https://chromedriver.chromium.org/downloads
    - Extract the downloaded zip to ~/Documents/chromedriver
    - Add the path to driver_path in settings.json


How to run:
    - Enter the product info to be fetched in products.csv
    - python3.6 trademap.py -t ti
    - python3.6 trademap.py -t qt
    - python3.6 trademap.py -t cmp


For help:
    - python3.6 trademap.py -h

    usage: trademap.py [-h] -t {ti,qt,cmp}

        optional arguments:
        -h, --help            show this help message and exit
        -t {ti,qt,cmp}, --type {ti,qt,cmp}
                                'ti': Trade Indicators; 'qt': Quarterly Time Series;
                                'cmp': Companies


Output:
    - Stored in output/<product-id>-<country>/<report-type>/*.xls
