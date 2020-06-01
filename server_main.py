
from flask import Flask
from flask import request
from Scraper import RecallSpider
from flask import jsonify
import json

app = Flask(__name__)


@app.route('/')
def hello_world():

    make = request.args.get('make')
    vin = request.args.get('vin')
    print(make, vin)
    if not make or not vin:
        response = {'Message': 'No VIN or Make or both given.'}
        return json.dumps(response), 400
    data = RecallSpider(make, vin).get_results()
    return json.dumps(data), 200


if __name__ == '__main__':
    app.run(debug=True)
