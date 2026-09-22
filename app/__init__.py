from pathlib import Path

from flask import Flask, render_template
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "warning"


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    from app import models
    from app.auth import bp as auth_bp
    from app.properties import bp as properties_bp
    from app.tenants import bp as tenants_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(properties_bp)
    app.register_blueprint(tenants_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(models.User, int(user_id))

    @app.context_processor
    def inject_brand():
        return {"brand_name": app.config["BRAND_NAME"]}

    @app.errorhandler(413)
    def upload_too_large(_error):
        return render_template("error.html", message="That upload is too large (16 MB maximum)."), 413

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", message="You do not have access to that page."), 403

    with app.app_context():
        try:
            db.create_all()
        except Exception:
            app.logger.exception(
                "Could not create tables. Start MySQL and check MYSQL_* in .env."
            )
            raise

    return app
