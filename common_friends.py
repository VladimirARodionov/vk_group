from settings import token, group_id, api_v, max_workers

from main import VkFriends


if __name__ == '__main__':
    with open('public_users.txt', encoding='utf-8') as f:
        lines = f.read().splitlines()
    a = VkFriends(token, group_id, api_v, max_workers)
    cf = a.common_friends(lines)
    #cf = a.common_friends(('205167060', '204740282', '11513365', '75282'))
