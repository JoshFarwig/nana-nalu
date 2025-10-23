import os

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from geoalchemy2 import alembic_helpers
from alembic import context
from dotenv import load_dotenv

from core.config import get_settings

# Load ENV's
load_dotenv()

# Get settings object, use it's database url
settings = get_settings(os.getenv("API_ENV", "dev"))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from models.base_model import Base

# IMPORTANT: Import all your models so they register with Base.metadata
from models.user_model import User
from models.surf_spot_model import SurfSpot
from models.spot_observation_model import SpotObservation

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

# NOTE: geoalchemy's alembic helper for the include object only check these tables names:
# if obj_type == "table" and (
#     name.startswith("geometry_columns")
#     or name.startswith("spatial_ref_sys")
#     or name.startswith("spatialite_history")
#     or name.startswith("sqlite_sequence")
#     or name.startswith("views_geometry_columns")
#     or name.startswith("virts_geometry_columns")
#     or name.startswith("idx_")
#     or name.startswith("gpkg_")
#     or name.startswith("vgpkg_")
# ):
#     return False
# return True
# If need be, create your own include_objects for your own specific postgis tables


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """

    # Use sync URL for Alembic
    url = config.set_main_option("sqlalchemy.url", settings.sync_database_url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=alembic_helpers.include_object,
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Create engine with sync URL
    config.set_main_option("sqlalchemy.url", settings.sync_database_url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=alembic_helpers.include_object,
            process_revision_directives=alembic_helpers.writer,
            render_item=alembic_helpers.render_item,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
