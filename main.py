import json
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from settings import token, group_id, api_v, max_workers, delay, deep, blacklist, group_uid


def force(f, delay=delay):
	"""При неудачном запросе сделать паузу и попробовать снова"""
	def tmp(*args, **kwargs):
		while True:
			try:
				res = f(*args, **kwargs)
				break
			except KeyError:
				time.sleep(delay)
		return res
	return tmp

class VkException(Exception):
	def __init__(self, message):
		self.message = message

	def __str__(self):
		return self.message


class VkFriends():
	"""
	Находит друзей, находит общих друзей
	"""
	parts = lambda lst, n=200: (lst[i:i + n] for i in iter(range(0, len(lst), n)))
	make_targets = lambda lst: ",".join(str(id) for id in lst)

	def __init__(self, *pargs):
		try:
			self.token, self.my_id, self.api_v, self.max_workers = pargs
			#self.my_name, self.my_last_name, self.photo = self.base_info([self.my_id])
			self.all_friends, self.count_friends = self.friends(self.my_id)
		except VkException as error:
			sys.exit(error)

	def request_url(self, method_name, parameters, access_token=True):
		"""read https://vk.com/dev/api_requests"""

		req_url = 'https://api.vk.com/method/{method_name}?{parameters}&v={api_v}'.format(
			method_name=method_name, api_v=self.api_v, parameters=parameters)

		if access_token:
			req_url = '{}&access_token={token}'.format(req_url, token=self.token)

		return req_url

	def base_info(self, ids):
		"""read https://vk.com/dev/users.get"""
		r = requests.get(self.request_url('users.get', 'user_ids=%s&fields=photo' % (','.join(map(str, ids))))).json()
		if 'error' in r.keys():
			raise VkException('Error message: %s Error code: %s' % (r['error']['error_msg'], r['error']['error_code']))
		r = r['response'][0]
		# Проверяем, если id из settings.py не деактивирован
		if 'deactivated' in r.keys():
			raise VkException("User deactivated")
		return r['first_name'], r['last_name'], r['photo']

	def friends(self, id):
		"""
		read https://vk.com/dev/friends.get
		Принимает идентификатор пользователя
		"""
		# TODO: слишком много полей для всего сразу, город и страна не нужны для нахождения общих друзей
		r = requests.get(self.request_url('groups.getMembers',
				'group_id=%s' % id)).json()['response']

		count = r['count']
		items = r['items']

		while (count > len(items)):
			r = requests.get(self.request_url('groups.getMembers',
											  'group_id=%(group)s&offset=%(offset)s' % {'group': str(id), 'offset': str(len(items))})).json()['response']
			for item in r['items']:
				items.append(item)

		#r = list(filter((lambda x: 'deactivated' not in x.keys()), r['items']))
		return items, count


	def all_users(self):
		result = []

		def worker():
			try:
				items = []
				for i in VkFriends.parts(list(self.all_friends)):
					print('i=' + str(i))
					source_ids = VkFriends.make_targets(i)
					while True:
						resp = requests.get(self.request_url('users.get',
															 'fields=city,country,home_town,contacts&user_ids=%(source)s' % {
																 'source': source_ids},
															 access_token=True)).json()
						if resp.get('error'):
							print(resp.get('error'))
							time.sleep(delay)
						else:
							r = resp['response']
							break

					for item in r:
						items.append(item)

				# r = list(filter((lambda x: 'deactivated' not in x.keys()), r['items']))
				return items
			except Exception as e:
				print(str(e))
				time.sleep(delay)

		def fill_result(r):
			with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
				try:
					result.append(r if r else None)
				except:
					pass

		fill_result(worker())

		return result


	def common_friends(self, userlist):
		"""
		read https://vk.com/dev/friends.getMutual and read https://vk.com/dev/execute
		Возвращает в словаре кортежи с инфой о цели и списком общих друзей с инфой
		"""
		result = []

		def worker(i, j):
			while True:
				try:
					target_uids = i
					if j in target_uids:
						target_uids.remove(j)
					for bl in blacklist:
						if str(bl) in target_uids:
							target_uids.remove(str(bl))
							print('Removed blacklisted id: ' + str(bl))
					resp = requests.get(self.request_url('friends.getMutual',
														 'source_uid=%(source)s&target_uids=%(target)s' % {
															 'source': j,
															 'target': VkFriends.make_targets(target_uids)},
														 access_token=True)).json()
					if resp.get('error'):
						print(resp.get('error'))
						time.sleep(delay)
					else:
						return resp['response']
						break
				except Exception as e:
					print(str(e))
					time.sleep(delay)

		def fill_result(index,r):
			with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
				for x, id in enumerate(index):
					try:
						result.append([id, r['common_friends']])
					except:
						pass

		for bl in blacklist:
			if str(bl) in userlist:
				userlist.remove(str(bl))
				print('Removed blacklisted id: ' + str(bl))
		with open('common_friends.txt', encoding='utf-8') as f:
			lines = f.read().splitlines()
		f.close()
		for l in lines:
			if str(l) in userlist:
				userlist.remove(str(l))
		for j in userlist:
			print('j=' + str(j))
			for i in VkFriends.parts(list(userlist)):
				print('i=' + str(i))
				worker_result = worker(i, j)
				result.append([j, worker_result[0]['common_friends']])
			#save to file
			with open('common_friends.txt', 'a', encoding='utf-8') as f:
				if not result:
					f.write("%s\n" % str(j))
				for item in result:
					f.write("%s;%s\n" % (str(j), item))

		return result

	def deep_friends(self, deep):
		"""
		Возвращает словарь с id пользователей, которые являются друзьями, или друзьями-друзей (и т.д. в зависимсти от
		deep - глубины поиска) указаннного пользователя
		"""
		result = {}

		@force
		def worker(i):	    
			r = requests.get(self.request_url('execute.deepFriends', 'targets=%s' % VkFriends.make_targets(i), access_token=True)).json()['response']
			for x, id in enumerate(i):
				result[id] = tuple(r[x]["items"]) if r[x] else None

		def fill_result(friends):
			with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
				[pool.submit(worker, i) for i in VkFriends.parts(friends)]

		for i in range(deep):
			if result:
				# те айди, которых нет в ключах + не берем id:None
				fill_result(list(set([item for sublist in result.values() if sublist for item in sublist]) - set(result.keys())))
			else:
				fill_result(requests.get(self.request_url('friends.get', 'user_id=%s' % self.my_id, access_token=True)).json()['response']["items"])

		return result

	def from_where_gender(self):
		"""
		Возвращает кортеж из 3х частей
		0 -  сколько всего/в% друзей в определнной локации (country, city)
		1 - список, содержащий количество друзей того или иного пола. Где индекс
			0 - пол не указан
			1 - женский;
			2 - мужской;
		2 - сколько друзей родилось в тот или иной день
		"""
		locations, all, genders, bdates = [{}, {}], [0, 0], [0, 0, 0], {}

		def calculate(dct, all):
			return {k: (dct[k], round(dct[k]/all * 100, 2)) for k, v in dct.items()}

		def constr(location, dct, ind):
			if location in dct.keys():
				place = dct[location]["title"]
				locations[ind][place] = 1 if place not in locations[ind] else locations[ind][place] + 1
				all[ind] += 1

		for i in self.all_friends.values():
			constr("country", i, 0)
			constr("city", i, 1)
			if "sex" in i.keys():
				genders[i["sex"]] += 1
			if "bdate" in i.keys():
				date = '.'.join(i["bdate"].split(".")[:2])
				bdates[date] = 1 if date not in bdates else bdates[date] + 1

		return (calculate(locations[0], all[0]), calculate(locations[1], all[1])), genders, bdates


	def write_json(self, json, filename):
		with open(filename+'.json',"w", encoding='utf-8') as f:
			f.write(json)

	def find_blacklist(self, userlist):
		for bl in list(userlist):
			print('bl=' + str(bl))
			while True:
				resp = requests.get(self.request_url('friends.getMutual',
												  'source_uid=%(source)s&target_uid=%(target)s' % {
													  'source': userlist[0],
													  'target': bl},
												  access_token=True)).json()
				if resp.get('error'):
					print(resp.get('error'))
					if (resp.get('error').get('error_code') == '15'):
						print('Added to blacklist from ' + bl)
				else:
					break


	def remove_from_group(self, userlist):
		for bl in list(userlist):
			print('bl=' + str(bl))
			while True:
				resp = requests.get(self.request_url('groups.removeUser',
												  'group_id=%(group)s&user_id=%(target)s' % {
													  'group': group_uid,
													  'target': bl},
												  access_token=True)).json()
				if resp.get('error'):
					print(resp.get('error'))
				else:
					print(resp.get('response'))
					break



if __name__ == '__main__':
	a = VkFriends(token, group_id, api_v, max_workers)

	with open('group_members.txt', 'w', encoding='utf-8') as f:
		for item in a.all_friends:
			f.write("%s\n" % item)

	all_users = a.all_users()[0]
	a.write_json(json.dumps(all_users, ensure_ascii=False), 'all_users')
	banned_users_ids = []
	city = []
	users_csv = []
	user_ids = []
	for user in all_users:
		if user.get('city'):
			city.append({'city_id': user.get('city').get('id'), 'city_name': user.get('city').get('title') if user.get('city').get('title') else None})
		if user.get('deactivated'):
			banned_users_ids.append(user.get('id'))
		else:
			users_csv.append(str(user.get('id')) + ';' + user.get('first_name') + ';' + user.get('last_name')+ ';' + (user.get('city').get('title') if user.get('city') else ''))
			if not user.get('is_closed'):
				user_ids.append(user.get('id'))

	with open('banned_users_ids.txt', 'w', encoding='utf-8') as f:
		for item in banned_users_ids:
			f.write("%s\n" % item)
	with open('city.txt', 'w', encoding='utf-8') as f:
		for item in city:
			f.write("%s\n" % item)
	with open('users.txt', 'w', encoding='utf-8') as f:
		for item in users_csv:
			f.write("%s\n" % item)

	with open('public_users.txt', 'w', encoding='utf-8') as f:
		for item in user_ids:
			f.write("%s\n" % item)

	#banned_users_ids.remove(1773012)
	#banned_users_ids.remove(101658562)
	#a.remove_from_group(banned_users_ids)

	# print(a.my_name, a.my_last_name, a.my_id, a.photo)
	#cf = a.common_friends(user_ids)
	#df = a.deep_friends(deep)
	#print(df)
	#VkFriends.save_load_deep_friends('deep_friends_dct', True, df)
	#print(pickle.load( open('deep_friends_dct', "rb" )))
	#print(a.from_where_gender())
