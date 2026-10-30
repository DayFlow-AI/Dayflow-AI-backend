import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from plan_board.routes import plan_board_router
from plan_board.ws import ws_router
from proj_settings.env_conf import settings
from user.oauth2_0.routes import oauth2_router
from user.routes import user_router

app = FastAPI(debug=True, title="DayFlow API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(user_router)
app.include_router(oauth2_router)
app.include_router(ws_router)

app.include_router(plan_board_router)

@app.exception_handler(OperationalError)
async def operational_error_handler(request: Request, exc: OperationalError):
    return JSONResponse(status_code=503, content={"detail": "database unavailable"})

if __name__ == "__main__":
    uvicorn.run(
        "main:app", reload=True, host=settings.host, port=settings.port, use_colors=True
    )
