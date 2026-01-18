from datetime import datetime

class LogQuery:
    def __init__(self, user_id: int, log_operation: str, log_operation_info: str):
        self.user_id = user_id
        self.log_operation = log_operation
        self.log_operation_info = log_operation_info
        self.log_dt = datetime.now()
