awk -F';' 'BEGIN { max = -999999 } { if ($2 > max) { max = $2; line = $0 } } END { print max, line }' aurinko.txt
awk -F';' 'BEGIN { max = -999999 } { if ($4 > max) { max = $4; line = $0 } } END { print max, line }' aurinko.txt