
encoding = 'ISO-8859-1'
with open('real_acct.txt', 'r', encoding=encoding) as f:
    line = f.readline()
    print(f"First line: {line}")
    print(f"Split by tab: {line.split('\t')}")
    print(f"Number of columns: {len(line.split('\t'))}")

    line2 = f.readline()
    print(f"Second line length: {len(line2.split('\t'))}")
