"""Strict Responses API schemas; semantic/evidence validation still runs locally."""
def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
def text(limit):return {'type':'string','minLength':1,'maxLength':limit}
def enum(values):return {'type':'string','enum':list(values)}
def arr(item,minimum=0,maximum=None):
    value={'type':'array','items':item,'minItems':minimum}
    if maximum is not None:value['maxItems']=maximum
    return value
def ids(values,minimum=0):return arr({'type':'integer','enum':list(values)},minimum)
def issue_schema(items,knowledge):
    from ai_analyzer import PROBLEM_TYPES
    from grouped_report import CATEGORIES
    refs=arr(enum([k['id'] for k in knowledge])) if knowledge else arr({'type':'string'},maximum=0)
    return obj({'issues':arr(obj({'title':text(90),'discussion':text(320),
        'category':enum([*CATEGORIES,'unresolved']),'problem_type':enum(PROBLEM_TYPES),
        'evidence_ids':ids([r['id'] for r in items],1),'knowledge_ids':refs}),1)})
def digest_schema(candidates):
    from grouped_report import CATEGORIES
    choices=list(range(len(candidates)))
    return obj({'groups':arr(obj({'category':enum(CATEGORIES),'candidate_ids':ids(choices,1),
                                'bullets':arr(text(280),1,4)}),maximum=5),
                'unresolved_candidate_ids':ids(choices),'overall_analysis':text(900)})
def normalization_schema(items):
    from ai_analyzer import TOPICS
    return obj({'items':arr(obj({'id':{'type':'integer','enum':[i['id'] for i in items]},
       'disposition':enum(['issue','uncertain','non_issue']),'topic':enum(TOPICS),
       'kind':enum(['reported_symptom','dissatisfaction','question','suggestion','chatter']),
       'evidence_quote':text(500),'retention_signal':{'type':'boolean'}}),len(items),len(items))})
REVIEW_SCHEMA=obj({'approved':{'type':'boolean'},'reasons':arr(enum([
    'unsupported_claim','mixed_topics','repetition','team_actions','unknown_abbreviation']))})
