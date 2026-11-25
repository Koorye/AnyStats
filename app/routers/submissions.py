from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import crud
from ..database import get_db
from ..response import ok
from ..schemas import SubmissionCreate
from ..security import client_ip, limiter, require_admin

router = APIRouter(prefix="/api/v1/submissions", tags=["submissions"])


@router.post("")
def create_submission(payload: SubmissionCreate, request: Request, conn: Connection = Depends(get_db)):
    """公开提交（同 IP 每小时限频 + 蜜罐字段）。"""
    if payload.website:
        raise HTTPException(status_code=400, detail="非法提交")
    limiter.check(client_ip(request))
    submission_id = crud.submissions.create_submission(conn, payload)
    return ok({"id": submission_id, "message": "登记成功"})


@router.get("")
def list_submissions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    country: str | None = None,
    affiliation_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    _: None = Depends(require_admin),
    conn: Connection = Depends(get_db),
):
    """登记明细（管理员）。"""
    rows, total = crud.submissions.list_submissions(
        conn,
        page=page,
        page_size=page_size,
        country=country,
        affiliation_type=affiliation_type,
        date_from=date_from,
        date_to=date_to,
    )
    return ok(
        {
            "items": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/{submission_id}")
def get_submission(submission_id: int, _: None = Depends(require_admin),
                   conn: Connection = Depends(get_db)):
    row = crud.submissions.get_submission(conn, submission_id)
    if row is None:
        raise HTTPException(status_code=404, detail="登记不存在")
    return ok(dict(row))
