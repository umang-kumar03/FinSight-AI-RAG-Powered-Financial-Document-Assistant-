"""Small labeled retrieval checks; never substitute these for real quality studies."""
from src.errors import ValidationError


def evaluate_retrieval(service, cases: list[dict], k: int = 4):
    if not cases:
        raise ValidationError('Provide at least one labeled query.')
    rows = []
    for case in cases:
        expected = {(item['source'], item['page']) for item in case['relevant']}
        if not expected:
            raise ValidationError('Each query requires at least one relevant source/page label.')
        retrieved = service.search(case['query'], k=k)
        hits = {(s.source, s.page) for s in retrieved}
        rank = next((i for i, s in enumerate(retrieved, 1)
                     if (s.source, s.page) in expected), None)
        rows.append({'query': case['query'], 'recall_at_k': len(hits & expected) / len(expected),
                     'reciprocal_rank': 1 / rank if rank else 0.0,
                     'retrieved': [{'source': s.source, 'page': s.page} for s in retrieved]})
    return {'k': k, 'cases': len(rows),
            'mean_recall_at_k': sum(r['recall_at_k'] for r in rows) / len(rows),
            'mean_reciprocal_rank': sum(r['reciprocal_rank'] for r in rows) / len(rows),
            'results': rows,
            'scope': 'Only these labeled fixtures; not an accuracy or generalization claim.'}
