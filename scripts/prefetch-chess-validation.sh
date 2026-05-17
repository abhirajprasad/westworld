#!/usr/bin/env bash
#
# Pre-Claude validation of pending chess moves.
#
# Runs before chess-arbiter SKILL.md. With full env access (env var expansion works
# here unlike in Claude's sandbox). Uses python-chess to validate each candidate
# move against the current FEN, writing results to .chess-pending/ for Claude to
# act on.
#
# Required env: WESTWORLD_REPO, GH_TOKEN (built-in in workflows)

set -euo pipefail

PENDING_DIR=".chess-pending"
mkdir -p "$PENDING_DIR"
# Clear stale pending state from prior runs
rm -f "$PENDING_DIR"/*.json

# Ensure python-chess is installed (workflow setup step should also install it)
if ! python3 -c "import chess" 2>/dev/null; then
  pip install --quiet python-chess
fi

# List all active games
ACTIVE_GAMES=$(gh api "repos/${WESTWORLD_REPO:-$(gh api repos/$GITHUB_REPOSITORY --jq .full_name)}/issues?labels=type:chess,chess:active&state=open&per_page=100" --paginate)

echo "$ACTIVE_GAMES" | jq -c '.[]' | while read -r ISSUE; do
  ISSUE_NUMBER=$(echo "$ISSUE" | jq -r '.number')

  # Load the game state file
  GAME_FILE=""
  for f in chess/games/*.json; do
    [ -e "$f" ] || continue
    if [ "$(jq -r '.issue_number' "$f" 2>/dev/null)" = "$ISSUE_NUMBER" ]; then
      GAME_FILE="$f"
      break
    fi
  done

  if [ -z "$GAME_FILE" ]; then
    echo "warn: no state file for issue $ISSUE_NUMBER; skipping" >&2
    continue
  fi

  GAME_ID=$(jq -r '.game_id' "$GAME_FILE")
  CURRENT_FEN=$(jq -r '.fen' "$GAME_FILE")
  TURN=$(jq -r '.turn' "$GAME_FILE")
  WHITE=$(jq -r '.white' "$GAME_FILE")
  BLACK=$(jq -r '.black' "$GAME_FILE")
  LAST_MOVE_AT=$(jq -r '.last_move_at' "$GAME_FILE")

  TURN_PLAYER=$([ "$TURN" = "white" ] && echo "$WHITE" || echo "$BLACK")

  # Get comments since last move
  COMMENTS=$(gh api "repos/${WESTWORLD_REPO}/issues/$ISSUE_NUMBER/comments?since=$LAST_MOVE_AT&per_page=100" --paginate)

  # Find the most recent comment from the player whose turn it is, containing a move marker
  MOVE_COMMENT=$(echo "$COMMENTS" | jq -c --arg user "$TURN_PLAYER" \
    '[.[] | select(.user.login == $user)] | sort_by(.created_at) | reverse | .[0]')

  if [ "$MOVE_COMMENT" = "null" ] || [ -z "$MOVE_COMMENT" ]; then
    continue
  fi

  COMMENT_BODY=$(echo "$MOVE_COMMENT" | jq -r '.body')
  COMMENT_ID=$(echo "$MOVE_COMMENT" | jq -r '.id')

  # Extract SAN move: prefer "**Move:** <san>" pattern, fallback to first SAN-shaped token
  SAN=$(echo "$COMMENT_BODY" | grep -oE '\*\*Move:\*\*[[:space:]]*[a-hKQRBNO][a-hOo0-9x+#=-]*' | head -1 | sed 's/\*\*Move:\*\*[[:space:]]*//')

  if [ -z "$SAN" ]; then
    # Fallback: check for resignation marker
    if echo "$COMMENT_BODY" | grep -qE '^\*\*Resign\*\*$'; then
      SAN="RESIGN"
    else
      # Fallback: first SAN-looking token in the body
      SAN=$(echo "$COMMENT_BODY" | grep -oE '\b(O-O(-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](=[QRBN])?[+#]?)\b' | head -1)
    fi
  fi

  if [ -z "$SAN" ]; then
    continue
  fi

  # Validate via python-chess
  VALIDATION=$(python3 <<EOF
import chess, json, sys
fen = """$CURRENT_FEN"""
san = """$SAN"""
board = chess.Board(fen)
if san == "RESIGN":
    result = {"legal": True, "kind": "resign", "new_status": "resigned"}
else:
    try:
        move = board.parse_san(san)
        board.push(move)
        if board.is_checkmate():
            new_status = "checkmate"
        elif board.is_stalemate():
            new_status = "stalemate"
        elif board.is_insufficient_material():
            new_status = "draw-insufficient"
        elif board.is_fifty_moves():
            new_status = "draw-50move"
        elif board.is_repetition(3):
            new_status = "draw-3fold"
        elif board.is_check():
            new_status = "check"
        else:
            new_status = "active"
        result = {
            "legal": True,
            "kind": "move",
            "san": san,
            "new_fen": board.fen(),
            "new_status": new_status,
        }
    except (ValueError, chess.IllegalMoveError, chess.AmbiguousMoveError, chess.InvalidMoveError) as e:
        result = {"legal": False, "san": san, "reason": str(e)}
print(json.dumps(result))
EOF
  )

  # Write the pending validation
  jq -n \
    --arg game_id "$GAME_ID" \
    --argjson issue_number "$ISSUE_NUMBER" \
    --argjson comment_id "$COMMENT_ID" \
    --arg by "$TURN_PLAYER" \
    --argjson validation "$VALIDATION" \
    --arg comment_body "$COMMENT_BODY" \
    --arg current_fen "$CURRENT_FEN" \
    '{
      game_id: $game_id,
      issue_number: $issue_number,
      candidate_move: ($validation + {
        comment_id: $comment_id,
        by: $by,
        comment_body: $comment_body,
        prior_fen: $current_fen
      })
    }' > "$PENDING_DIR/$GAME_ID.json"

done

echo "prefetch-chess-validation: wrote $(ls "$PENDING_DIR"/*.json 2>/dev/null | wc -l) pending validations"
