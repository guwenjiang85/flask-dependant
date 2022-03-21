from flask import Flask
from flask_dependant.params import Path, Query, Body, Header


app = Flask(__name__)


#  ============  simple examples ============
@app.route('/params_test/<m>')
def params_test(
    m: int = Path(..., alias="m"),   # or m: int
):