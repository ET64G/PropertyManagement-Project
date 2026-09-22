from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import HiddenField, PasswordField, StringField
from wtforms.validators import DataRequired, Email, Length

from app import db
from app.models import User

bp = Blueprint("auth", __name__)


class RegisterForm(FlaskForm):
    full_name = StringField(
        "Full name",
        validators=[DataRequired(), Length(max=120)],
    )
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=128)],
    )


class LoginForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    password = PasswordField("Password", validators=[DataRequired()])
    next_url = HiddenField()


def home_for(user):
    if user.role == "landlord":
        return url_for("properties.list_properties")
    return url_for("properties.my_property")


def safe_next(target, user):
    if (
        isinstance(target, str)
        and target.startswith("/")
        and not target.startswith("//")
        and "\\" not in target
    ):
        return target
    return home_for(user)


def landlord_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "landlord":
            return render_template(
                "error.html",
                message="You do not have access to that page.",
            ), 403
        return view(*args, **kwargs)

    return wrapped


def tenant_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "tenant":
            return render_template(
                "error.html",
                message="You do not have access to that page.",
            ), 403
        return view(*args, **kwargs)

    return wrapped


@bp.route("/")
def landing():
    return render_template("landing.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
            return render_template("register.html", form=form)
        user = User(
            email=email,
            full_name=form.full_name.data.strip(),
            role="landlord",
            assigned_property_id=None,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Your landlord account is ready.", "success")
        return redirect(url_for("properties.list_properties"))
    return render_template("register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        if user is None or not user.check_password(form.password.data):
            flash("Email or password is incorrect.", "danger")
            return render_template("login.html", form=form)
        login_user(user)
        return redirect(safe_next(form.next_url.data, user))
    if request.method == "GET":
        form.next_url.data = request.args.get("next", "")
    return render_template("login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.landing"))
