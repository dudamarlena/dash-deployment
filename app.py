from dash import Dash, html

app = Dash(__name__)
server = app.server

app.layout = html.Div("Hello from Dash on Azure")

if __name__ == "__main__":
    app.run(debug=True)