from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy.exc import IntegrityError
from wtforms import PasswordField, SelectField, StringField
from wtforms.validators import DataRequired, Email, Length

from app import db
from app.auth import landlord_required
from app.models import Property, User

bp = Blueprint("tenants", __name__)


class TenantForm(FlaskForm):
    full_name = StringField(
        "Full name",
        validators=[DataRequired(), Length(max=120)],
    )
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    password = PasswordField(
        "Temporary password",
        validators=[DataRequired(), Length(min=8, max=128)],
    )
    property_id = SelectField(
        "Property",
        coerce=int,
        validators=[DataRequired()],
    )


@bp.route("/tenants/new", methods=["GET", "POST"])
@landlord_required
def create_tenant():
    properties = (
        Property.query.filter_by(landlord_id=current_user.id)
        .order_by(Property.title)
        .all()
    )
    form = TenantForm()
    form.property_id.choices = [(prop.id, f"{prop.title} — {prop.city}") for prop in properties]
    if properties and form.validate_on_submit():
        selected = next((prop for prop in properties if prop.id == form.property_id.data), None)
        if selected is None or selected.landlord_id != current_user.id:
            flash("Choose one of your properties.", "danger")
            return render_template("tenant_form.html", form=form, properties=properties)
        email = form.email.data.strip().lower()
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
            return render_template("tenant_form.html", form=form, properties=properties)
        tenant = User(
            email=email,
            full_name=form.full_name.data.strip(),
            role="tenant",
            assigned_property_id=selected.id,
        )
        tenant.set_password(form.password.data)
        db.session.add(tenant)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("An account with that email already exists.", "danger")
            return render_template("tenant_form.html", form=form, properties=properties)
        flash("Tenant account created.", "success")
        return redirect(url_for("properties.list_properties"))
    return render_template("tenant_form.html", form=form, properties=properties)
