# infrastructure/persistence/repositories

Concrete repository **implementations** that satisfy the interfaces in
`app/domain/repositories/`, using SQLAlchemy + the ORM models in `../orm/`.
Example: `media_asset_repository.py` → `SqlAlchemyMediaAssetRepository`. These
map between ORM rows and domain entities and are injected into use cases by
`app/api/v1/dependencies/providers.py`.
