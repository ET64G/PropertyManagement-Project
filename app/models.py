from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint("role IN ('landlord', 'tenant')", name="ck_users_role"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    # Circular FK with properties: created in a follow-up ALTER so create_all succeeds.
    assigned_property_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "properties.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_users_assigned_property_id",
        ),
        nullable=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    owned_properties = db.relationship(
        "Property",
        back_populates="landlord",
        foreign_keys="Property.landlord_id",
    )
    assigned_property = db.relationship(
        "Property",
        back_populates="tenants",
        foreign_keys=[assigned_property_id],
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_landlord(self) -> bool:
        return self.role == "landlord"

    @property
    def is_tenant(self) -> bool:
        return self.role == "tenant"


class Property(db.Model):
    __tablename__ = "properties"
    __table_args__ = (
        db.CheckConstraint("bedrooms >= 0", name="ck_properties_bedrooms"),
        db.CheckConstraint("bathrooms >= 0", name="ck_properties_bathrooms"),
        db.CheckConstraint(
            "status IN ('available', 'occupied')",
            name="ck_properties_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    landlord_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_properties_landlord_id"),
        nullable=False,
    )
    title = db.Column(db.String(120), nullable=False)
    address_line = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    bedrooms = db.Column(db.SmallInteger, nullable=False)
    bathrooms = db.Column(db.SmallInteger, nullable=False)
    has_garden = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.text("0"),
    )
    status = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    landlord = db.relationship(
        "User",
        back_populates="owned_properties",
        foreign_keys=[landlord_id],
    )
    tenants = db.relationship(
        "User",
        back_populates="assigned_property",
        foreign_keys="User.assigned_property_id",
    )
    images = db.relationship(
        "PropertyImage",
        back_populates="listing",
        cascade="all, delete-orphan",
        order_by="PropertyImage.id",
    )

    @property
    def primary_image(self):
        primary = next((image for image in self.images if image.is_primary), None)
        if primary is not None:
            return primary
        return self.images[0] if self.images else None

    @property
    def garden_label(self) -> str:
        return "Yes" if self.has_garden else "No"


class PropertyImage(db.Model):
    __tablename__ = "property_images"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    property_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "properties.id",
            ondelete="CASCADE",
            name="fk_property_images_property_id",
        ),
        nullable=False,
    )
    file_path = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(255), nullable=True)
    is_primary = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.text("0"),
    )

    listing = db.relationship("Property", back_populates="images")

    @property
    def stored_name(self) -> str:
        return self.file_path.rsplit("/", 1)[-1]
