from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from geoalchemy2 import alembic_helpers
from alembic import context
from dotenv import load_dotenv

from core.config import load_settings

# load ENV's
load_dotenv()

# get settings object, use it's database url (alembic needs DB access like API/Worker)
settings = load_settings("api")

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# interpret the config file for Python logging,
# this line sets up loggers for alembic
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from models.base_model import Base

# IMPORTANT: import all your models so they register with Base.metadata
# Import from models package to get all models in correct dependency order
import models  # noqa: F401

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

    Calls to context.execute() here, emits the given string to the
    script output.

    """

    # use sync URL for Alembic
    url = config.set_main_option("sqlalchemy.url", settings.db.get_sync_url())
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
    # create engine with sync URL
    config.set_main_option("sqlalchemy.url", settings.db.get_sync_url())

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
