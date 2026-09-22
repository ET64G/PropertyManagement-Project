import shutil
import uuid
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange

from app import db
from app.auth import landlord_required, tenant_required
from app.models import Property, PropertyImage

bp = Blueprint("properties", __name__)

JPEG_EXTENSIONS = {".jpg", ".jpeg"}
JPEG_MIMETYPES = {"image/jpeg", "image/pjpeg", "image/jpg"}


class PropertyForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=120)])
    address_line = StringField(
        "Address",
        validators=[DataRequired(), Length(max=255)],
    )
    city = StringField("City", validators=[DataRequired(), Length(max=100)])
    description = TextAreaField("Description", validators=[Length(max=5000)])
    bedrooms = IntegerField(
        "Bedrooms",
        validators=[InputRequired(), NumberRange(min=0, max=100)],
    )
    bathrooms = IntegerField(
        "Bathrooms",
        validators=[InputRequired(), NumberRange(min=0, max=100)],
    )
    has_garden = SelectField(
        "Garden",
        choices=[("no", "No"), ("yes", "Yes")],
        validators=[DataRequired()],
    )
    status = SelectField(
        "Status",
        choices=[("available", "Available"), ("occupied", "Occupied")],
        validators=[DataRequired()],
    )


def get_owned_property(property_id):
    prop = db.session.get(Property, property_id)
    if prop is None or prop.landlord_id != current_user.id:
        abort(404)
    return prop


def can_view_property(prop) -> bool:
    if not current_user.is_authenticated:
        return False
    if current_user.role == "landlord":
        return prop.landlord_id == current_user.id
    if current_user.role == "tenant":
        return prop.id == current_user.assigned_property_id
    return False


def _selected_files():
    return [item for item in request.files.getlist("images") if item and item.filename]


def _jpeg_error(files):
    for storage in files:
        name = storage.filename or "file"
        extension = Path(name).suffix.lower()
        if extension not in JPEG_EXTENSIONS:
            return f"{name} is not a JPEG. Use a .jpg or .jpeg file."
        mimetype = (storage.mimetype or "").split(";")[0].strip().lower()
        if mimetype not in JPEG_MIMETYPES:
            return f"{name} must be uploaded as a JPEG image."
        header = storage.stream.read(3)
        storage.stream.seek(0)
        if header != b"\xff\xd8\xff":
            return f"{name} is not a valid JPEG file."
    return None


def _apply_form(prop, form):
    prop.title = form.title.data.strip()
    prop.address_line = form.address_line.data.strip()
    prop.city = form.city.data.strip()
    description = (form.description.data or "").strip()
    prop.description = description or None
    prop.bedrooms = form.bedrooms.data
    prop.bathrooms = form.bathrooms.data
    prop.has_garden = form.has_garden.data == "yes"
    prop.status = form.status.data


def _fill_form(form, prop):
    form.title.data = prop.title
    form.address_line.data = prop.address_line
    form.city.data = prop.city
    form.description.data = prop.description or ""
    form.bedrooms.data = prop.bedrooms
    form.bathrooms.data = prop.bathrooms
    form.has_garden.data = "yes" if prop.has_garden else "no"
    form.status.data = prop.status


def _save_images(prop, files):
    folder = Path(current_app.config["UPLOAD_FOLDER"]) / str(prop.id)
    folder.mkdir(parents=True, exist_ok=True)
    has_primary = any(image.is_primary for image in prop.images)
    saved_any = False
    written = []
    try:
        for storage in files:
            filename = f"{uuid.uuid4().hex}.jpg"
            path = folder / filename
            storage.save(path)
            written.append(path)
            image = PropertyImage(
                property_id=prop.id,
                file_path=f"uploads/{prop.id}/{filename}",
                is_primary=not has_primary and not saved_any,
            )
            saved_any = True
            db.session.add(image)
    except Exception:
        for path in written:
            if path.is_file():
                path.unlink()
        raise


def _unlink_image(image):
    path = Path(current_app.config["UPLOAD_FOLDER"]) / str(image.property_id) / image.stored_name
    if path.is_file():
        path.unlink()


@bp.route("/properties")
@landlord_required
def list_properties():
    properties = (
        Property.query.filter_by(landlord_id=current_user.id)
        .order_by(Property.created_at.desc())
        .all()
    )
    return render_template("property_list.html", properties=properties)


@bp.route("/properties/new", methods=["GET", "POST"])
@landlord_required
def create_property():
    form = PropertyForm()
    if form.validate_on_submit():
        files = _selected_files()
        error = _jpeg_error(files)
        if error:
            flash(error, "danger")
            return render_template("property_form.html", form=form, prop=None)
        prop = Property(landlord_id=current_user.id, title="", address_line="", city="", bedrooms=0, bathrooms=0, status="available")
        _apply_form(prop, form)
        db.session.add(prop)
        try:
            db.session.flush()
            _save_images(prop, files)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Failed to save property")
            flash("Could not save the property.", "danger")
            return render_template("property_form.html", form=form, prop=None)
        flash("Property saved.", "success")
        return redirect(url_for("properties.property_detail", property_id=prop.id))
    return render_template("property_form.html", form=form, prop=None)


@bp.route("/properties/<int:property_id>")
@landlord_required
def property_detail(property_id):
    prop = get_owned_property(property_id)
    return render_template("property_detail.html", prop=prop, read_only=False)


@bp.route("/properties/<int:property_id>/edit", methods=["GET", "POST"])
@landlord_required
def edit_property(property_id):
    prop = get_owned_property(property_id)
    form = PropertyForm()
    if form.validate_on_submit():
        files = _selected_files()
        error = _jpeg_error(files)
        if error:
            flash(error, "danger")
            return render_template("property_form.html", form=form, prop=prop)
        _apply_form(prop, form)
        try:
            _save_images(prop, files)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Failed to update property")
            flash("Could not update the property.", "danger")
            return render_template("property_form.html", form=form, prop=prop)
        flash("Property updated.", "success")
        return redirect(url_for("properties.property_detail", property_id=prop.id))
    if request.method == "GET":
        _fill_form(form, prop)
    return render_template("property_form.html", form=form, prop=prop)


@bp.route("/properties/<int:property_id>/delete", methods=["POST"])
@landlord_required
def delete_property(property_id):
    prop = get_owned_property(property_id)
    property_folder = prop.id
    db.session.delete(prop)
    db.session.commit()
    folder = Path(current_app.config["UPLOAD_FOLDER"]) / str(property_folder)
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    flash("Property deleted.", "success")
    return redirect(url_for("properties.list_properties"))


@bp.route("/properties/<int:property_id>/images/<int:image_id>/delete", methods=["POST"])
@landlord_required
def delete_image(property_id, image_id):
    prop = get_owned_property(property_id)
    image = db.session.get(PropertyImage, image_id)
    if image is None or image.property_id != prop.id:
        abort(404)
    was_primary = image.is_primary
    _unlink_image(image)
    db.session.delete(image)
    db.session.flush()
    if was_primary:
        replacement = PropertyImage.query.filter_by(property_id=prop.id).first()
        if replacement is not None:
            replacement.is_primary = True
    db.session.commit()
    flash("Photo removed.", "success")
    return redirect(url_for("properties.property_detail", property_id=prop.id))


@bp.route("/my-property")
@tenant_required
def my_property():
    prop = None
    if current_user.assigned_property_id:
        prop = db.session.get(Property, current_user.assigned_property_id)
    return render_template("property_detail.html", prop=prop, read_only=True)


@bp.route("/uploads/<int:property_id>/<filename>")
@login_required
def serve_upload(property_id, filename):
    if "/" in filename or "\\" in filename or filename.startswith("."):
        abort(404)
    prop = db.session.get(Property, property_id)
    if prop is None or not can_view_property(prop):
        abort(404)
    relative = f"uploads/{property_id}/{filename}"
    image = PropertyImage.query.filter_by(property_id=property_id, file_path=relative).first()
    if image is None:
        abort(404)
    directory = Path(current_app.config["UPLOAD_FOLDER"]) / str(property_id)
    return send_from_directory(directory, filename)
