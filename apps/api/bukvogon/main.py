from fastapi import FastAPI

from bukvogon.api.routes import router as v1_router

app = FastAPI(title='BukvoGon API', version='0.1.0')


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


app.include_router(v1_router, prefix='/v1')
