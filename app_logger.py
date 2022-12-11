import logging

_log_format = f"%(asctime)s - [%(levelname)s] - %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s"


def get_file_handler(name):
    file_handler = logging.FileHandler(f"{name}.log")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(_log_format))
    return file_handler


def get_stream_handler():
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter(_log_format))
    return stream_handler


def get_logger(name):
    local_logger = logging.getLogger(name)
    local_logger.setLevel(logging.INFO)
    local_logger.addHandler(get_file_handler(name))
    local_logger.addHandler(get_stream_handler())
    return local_logger


def main():
    local_logger = get_logger('test_logger')
    local_logger.info("start")
    # package1.process(msg="сообщение")
    local_logger.warning("Warning")
    local_logger.info("finish")


# Включаем логирование, чтобы не пропустить важные сообщения
logger = get_logger("MyMTLWallet_bot")

if __name__ == "__main__":
    main()
