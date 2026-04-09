from dash import Dash, html

app = Dash(__name__)
server = app.server

app.layout = html.Div("Hello from Dash on Azure. Adding more text to test commit....")

if __name__ == "__main__":
    app.run(debug=True)