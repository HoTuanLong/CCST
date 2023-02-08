if __name__ == '__main__':
    for i in range(6):
        f = open(f"/home/ubuntu/long.ht/CCST/val{i}.txt", "r")
        f2 = open(f'/home/ubuntu/long.ht/CCST/val{i}_result.txt', 'w')
        for x in f:
            x = x.strip()
            b = str(x + " " + x.split('/')[7] + "\n")
            print(b)
            f2.write(b)
        f.close()
        f2.close()