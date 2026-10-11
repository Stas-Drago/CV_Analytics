from surveillance.query.router import QueryRouter


class AnswerService:
    def __init__(self, router: QueryRouter) -> None:
        self.router = router

    def plan(self, request: str) -> dict[str, str]:
        target = self.router.route(request)
        return {"target": target.value, "status": "planned"}
