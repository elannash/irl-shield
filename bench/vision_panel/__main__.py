"""Local protocol artifacts only; no grader, model, render or GPU dispatch."""
import argparse
import json

from .budget import counts, initial
from .pack import seal, skeleton, validate_plan
from .protocol import load, verify_card, write_once
from .scoring import reveal


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('request'); a.add_argument('destination')
    a = sub.add_parser('budget-init'); a.add_argument('destination')
    a = sub.add_parser('validate'); a.add_argument('plan')
    a = sub.add_parser('seal'); a.add_argument('plan'); a.add_argument('public'); a.add_argument('private')
    a = sub.add_parser('verify-card'); a.add_argument('directory')
    a = sub.add_parser('reveal'); a.add_argument('public'); a.add_argument('private'); a.add_argument('round'); a.add_argument('map_sha256')
    args = p.parse_args()
    if args.command == 'request':
        write_once(args.destination, skeleton()); result = {'status': 'MISSING_INPUTS', 'request': args.destination, 'cards_generated': 0}
    elif args.command == 'budget-init':
        state = initial(); write_once(args.destination, state); result = counts(state)
    elif args.command == 'validate':
        result = validate_plan(load(args.plan))
    elif args.command == 'seal':
        result = seal(load(args.plan), args.public, args.private)
    elif args.command == 'verify-card':
        card = verify_card(args.directory); result = {'card_digest': card['card_digest'], 'item_id': card['item_id']}
    else:
        result = reveal(args.public, args.private, args.round, args.map_sha256)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
