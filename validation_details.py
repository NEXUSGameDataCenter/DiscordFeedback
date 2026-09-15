"""Only developer-defined validation messages are safe to log."""
SAFE_MESSAGES={
 'Classification omitted or added messages','Invalid message id','Unknown/duplicate message id',
 'Invalid classification','Invalid kind','Evidence must be an exact source excerpt','Invalid retention flag',
 'Invalid issue','Invalid issue title','Invalid issue discussion','Invalid issue type','Missing issues',
 'Missing evidence','Unknown knowledge','Missing, duplicate or unknown evidence','Invalid overall object',
 'Invalid groups','Invalid unresolved ids','Invalid overall analysis','Invalid group','Invalid category',
 'Missing group ids','Invalid bullets','Missing merged issues','Invalid candidate ids',
}
def validation_detail(exc):
    message=str(exc)
    return message if message in SAFE_MESSAGES else 'validation_failed'
