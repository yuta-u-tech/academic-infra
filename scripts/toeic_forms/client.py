"""Forms API / Drive API 呼び出し（ネットワークを伴う薄いラッパー）。

組み立て済みの batchUpdate リクエスト（builder.py）を実際に送るだけで、
リクエスト内容の妥当性はテストしやすいよう builder.py 側に寄せてある。
"""
from __future__ import annotations


def create_form(forms_service, title: str) -> tuple[str, str]:
    """空のFormを作り、(formId, responderUri) を返す。

    forms.create は info.title のみ受け付ける（documentTitle 等は後から
    別リクエストで変える必要がある）。responderUri（回答用の公開URL）は
    formId から機械的に組み立てられる文字列ではない（Google が別に発行する、
    "1FAIpQLS..." で始まる別IDを使う）。実APIで確認済み — 必ず create()/get()
    のレスポンスからそのまま読むこと。
    """
    result = forms_service.forms().create(body={"info": {"title": title}}).execute()
    return result["formId"], result["responderUri"]


def apply_requests(forms_service, form_id: str, requests: list[dict]) -> None:
    if not requests:
        return
    forms_service.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()


def list_responses(forms_service, form_id: str) -> list[dict]:
    """Formへの回答を全件取る（ページングを吸収する）。"""
    responses: list[dict] = []
    page_token = None
    while True:
        result = (
            forms_service.forms()
            .responses()
            .list(formId=form_id, pageToken=page_token)
            .execute()
        )
        responses.extend(result.get("responses", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return responses


def edit_url(form_id: str) -> str:
    return f"https://docs.google.com/forms/d/{form_id}/edit"


def restrict_access(drive_service, form_id: str, allowed_emails: list[str]) -> None:
    """特定のGoogleアカウントのみ回答可にする。

    Form は API 作成直後は所有者以外アクセス不可（非公開）なので、ここでは
    「許可した知人にreader権限を明示的に付与する」だけでよい —
    「anyone with the link」等の広い共有には決してしない。
    """
    for email in allowed_emails:
        drive_service.permissions().create(
            fileId=form_id,
            body={"type": "user", "role": "reader", "emailAddress": email},
            sendNotificationEmail=False,
        ).execute()
