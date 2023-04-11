class NoAPIAnswerError(Exception):
    """No answer from API"""
    pass


class BotSendMessageError(Exception):
    """Error with sending message through bot"""
    pass
