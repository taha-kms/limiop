from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.db.session import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database = Database(app_settings.database_url)
        application.state.database = database
        try:
            yield
        finally:
            await database.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        debug=app_settings.debug,
        lifespan=lifespan,
    )
    application.state.settings = app_settings

    @application.exception_handler(RequestValidationError)
    async def scrub_validation_errors(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """The default handler echoes the rejected value back as `input` on
        every error entry (and `ctx`, which can carry it too, e.g.
        `min_length`'s companion value). That is fine for a malformed UUID
        and not fine for a password, so both are stripped here rather than
        in the schema — a field-level workaround would still leak, however
        the constraint that rejected the value is expressed."""
        errors = [
            {key: value for key, value in error.items() if key not in ("input", "ctx")}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=jsonable_encoder({"detail": errors}),
        )

    application.include_router(api_router)
    return application


app = create_app()
