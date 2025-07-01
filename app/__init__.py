from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
import datetime # Import datetime

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()

def create_app(config_class='config.Config'):
    """Construct the core application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize Flask extensions
    db.init_app(app)
    migrate.init_app(app, db)

    with app.app_context():
        # Import models first, as routes might depend on them
        from . import models

        # Register the main Blueprint from routes.py
        from .routes import bp as main_blueprint
        app.register_blueprint(main_blueprint)

        # Register context processors to make variables/functions available in all templates
        @app.context_processor
        def inject_global_vars():
            return {
                'utcnow': datetime.datetime.utcnow
            }

        # Create database tables for our data models if they don't exist.
        # For production, Flask-Migrate (alembic) should be used to manage schema changes.
        # db.create_all()

        # Optionally, initialize store hours if they are not already set.
        # This could also be a CLI command or done on first request to a specific page.
        # if not models.StoreHours.query.first() and models.StoreHours.query.count() < 7:
        #     models.StoreHours.initialize_hours()

        return app
