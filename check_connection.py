"""Run after .env + schema setup. --ai makes one small paid Gemini API request."""
import argparse
import asyncio

async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ai',action='store_true')
    parser.add_argument('--report-ai',action='store_true',help='Paid synthetic report analysis and evidence-review check')
    args=parser.parse_args()
    import config
    from database import Database
    from ai_analyzer import AIAnalyzer
    config.validate(database_only=True)
    db=Database(config.SUPABASE_URL,config.SUPABASE_SECRET_KEY)
    try:
        await db.init();print('PASS: Supabase schema and backend permissions')
    finally:await db.close()
    if args.ai or args.report_ai:
        if not config.GEMINI_API_KEY:raise ValueError('GEMINI_API_KEY is required')
        ai=AIAnalyzer(config.GEMINI_API_KEY,config.GEMINI_MODEL)
        try:
            result=await ai._json('ตอบ JSON เท่านั้น: {"ok":true}',{})
            if result!={'ok':True}:raise RuntimeError('Unexpected AI response')
            print('PASS: '+config.GEMINI_MODEL+' live response')
            if args.report_ai:
                from discussion_report import DiscussionError
                rows=[{'id':1,'content':'อยากให้มีกิจกรรมลดต้นทุนการทำของอีกครั้ง'},
                      {'id':2,'content':'วันนี้เข้าโหมด Total War ไม่ได้'}]
                issues=await ai.analyze_discussions(rows,[])
                digest=await ai.summarize_overall(issues,{'total':2,'pending_classification':0,'pending_extraction':0})
                print('PASS: report analysis, evidence validation and review; groups='+str(len(digest['groups'])))
        finally:await ai.close()
if __name__=='__main__':
    from ai_analyzer import AIResponseError
    from http_client import RemoteError
    from discussion_report import DiscussionError
    try:
        asyncio.run(main())
    except (AIResponseError, RemoteError, DiscussionError) as exc:
        print('FAIL: ' + str(exc))
        raise SystemExit(1)
