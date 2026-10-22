"""Add Cloudinary metadata and review image storage."""
from alembic import op
import sqlalchemy as sa


revision = "y0a1b2c3d4e5"
down_revision = "x9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("product_images", sa.Column("secure_url", sa.String(1000), nullable=True))
    op.add_column("product_images", sa.Column("cloudinary_public_id", sa.String(500), nullable=True))
    op.create_index("ix_product_images_cloudinary_public_id", "product_images", ["cloudinary_public_id"], unique=False)
    op.add_column("content_blocks", sa.Column("image_public_id", sa.String(500), nullable=True))
    op.add_column("return_evidence", sa.Column("secure_url", sa.String(1000), nullable=True))
    op.add_column("return_evidence", sa.Column("cloudinary_public_id", sa.String(500), nullable=True))
    op.add_column("return_evidence", sa.Column("cloudinary_type", sa.String(30), nullable=True))
    op.create_index("ix_return_evidence_cloudinary_public_id", "return_evidence", ["cloudinary_public_id"], unique=False)
    op.create_table(
        "review_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("secure_url", sa.String(length=1000), nullable=False),
        sa.Column("cloudinary_public_id", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=160), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cloudinary_public_id"),
    )
    op.create_index("ix_review_images_review_id", "review_images", ["review_id"], unique=False)
    op.create_index("ix_review_images_cloudinary_public_id", "review_images", ["cloudinary_public_id"], unique=False)


def downgrade():
    op.drop_index("ix_review_images_cloudinary_public_id", table_name="review_images")
    op.drop_index("ix_review_images_review_id", table_name="review_images")
    op.drop_table("review_images")
    op.drop_index("ix_return_evidence_cloudinary_public_id", table_name="return_evidence")
    op.drop_column("return_evidence", "cloudinary_type")
    op.drop_column("return_evidence", "cloudinary_public_id")
    op.drop_column("return_evidence", "secure_url")
    op.drop_column("content_blocks", "image_public_id")
    op.drop_index("ix_product_images_cloudinary_public_id", table_name="product_images")
    op.drop_column("product_images", "cloudinary_public_id")
    op.drop_column("product_images", "secure_url")
