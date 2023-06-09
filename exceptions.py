class NoAPIAnswerError(Exception):
    """No answer from API"""
    pass


class BotSendMessageError(Exception):
    """Error with sending message through bot"""
    pass


class JSONError(Exception):
    """Error with JSON"""
    pass


class APIRequestError(Exception):
    """Error with request to API"""
    pass
