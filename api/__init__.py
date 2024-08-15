import logging
from flask import Flask
from flask_cors import CORS
from concurrent.futures import ProcessPoolExecutor
from .config import config

max_concurrent_conversations = 8
executor = ProcessPoolExecutor(max_workers=max_concurrent_conversations)

user_sessions = {}


def create_app(config_name='default'):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config[config_name])

    CORS(app)

    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(message)s')

    with app.app_context():
        from .routes import routes_blueprint
        app.register_blueprint(routes_blueprint)

        return app
