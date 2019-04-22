
if __name__ == '__main__':
    with open('group_members.txt', encoding='utf-8') as f:
        all_members = f.read().splitlines()
    with open('members_free_journal.txt', encoding='utf-8') as f:
        minus_members = f.read().splitlines()
    all_members_minus = [x for x in all_members if x not in minus_members]
    with open('group_members_minus.txt', 'w', encoding='utf-8') as f:
        for item in all_members_minus:
            f.write("%s\n" % item)

