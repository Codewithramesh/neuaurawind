from alembic import context
from sqlalchemy import create_engine, pool
from backend.app.config import Settings
from backend.app.models import Base
from backend.app.storage import private_directory

config = context.config
settings = Settings()
private_directory(settings.data_dir)
url = settings.database_url
if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
