"""Structured stdout logging for correct Railway severity, without duplicate handlers."""
import json
import logging
import sys
class RailwayFormatter(logging.Formatter):
    def format(self,record):
        result={'level':record.levelname.lower(),'logger':record.name,'message':record.getMessage()}
        if record.exc_info:result['exception_type']=record.exc_info[0].__name__
        return json.dumps(result,ensure_ascii=False)
def configure_logging():
    handler=logging.StreamHandler(sys.stdout)
    handler.setFormatter(RailwayFormatter())
    logging.basicConfig(level=logging.INFO,handlers=[handler],force=True)
