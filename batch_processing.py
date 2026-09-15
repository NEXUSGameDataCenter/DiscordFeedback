"""Bounded splitting of invalid AI batches; preserve successful siblings."""
import asyncio
import logging
import time

async def process_batch(items,call,deadline,stage,max_depth=2):
    from discussion_report import failure_code
    results=[];failed=[];errors=[];fatal=False
    async def visit(batch,depth):
        nonlocal fatal
        if fatal or time.monotonic()>=deadline:
            failed.extend(r['id'] for r in batch)
            if not fatal:errors.append({'stage':stage,'code':'timeout'})
            return
        try:
            async with asyncio.timeout(max(0.01,deadline-time.monotonic())):
                values=await call(batch)
            results.extend(values)
        except Exception as exc:
            code=failure_code(exc)
            detail=getattr(exc,'detail','')
            logging.getLogger(__name__).warning('%s failed: code=%s detail=%s count=%s depth=%s',stage,code,detail,len(batch),depth)
            if code in ('schema_invalid','review_rejected') and len(batch)>1 and depth<max_depth:
                middle=len(batch)//2
                await visit(batch[:middle],depth+1)
                await visit(batch[middle:],depth+1)
            else:
                failed.extend(r['id'] for r in batch)
                errors.append({'stage':stage,'code':code,'detail':detail,'source_ids':[r['id'] for r in batch]})
                fatal=code not in ('schema_invalid','review_rejected','timeout')
    await visit(items,0)
    return results,failed,errors,fatal
