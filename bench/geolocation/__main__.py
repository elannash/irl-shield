import argparse

from .protocol import aggregate, freeze, write_new


def main():
    parser = argparse.ArgumentParser(description='Offline preregistered geolocation red team')
    commands = parser.add_subparsers(dest='command', required=True)
    bind = commands.add_parser('freeze', help='Bind actual exporter pairs before predictions')
    bind.add_argument('--preregistration', required=True)
    bind.add_argument('--pairs', required=True)
    bind.add_argument('--root', required=True)
    bind.add_argument('--output', required=True)
    score = commands.add_parser('score', help='Write aggregate-only JSON from paired results')
    score.add_argument('--preregistration', required=True)
    score.add_argument('--plan', required=True)
    score.add_argument('--results', required=True)
    score.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'freeze':
        freeze(args.preregistration, args.pairs, args.root, args.output)
    else:
        write_new(args.output, aggregate(args.preregistration, args.plan, args.results))


if __name__ == '__main__':
    main()
