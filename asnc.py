import asyncio
from aiohttp import web
import asyncpg

routes = web.RouteTableDef()


#db create
async def install(user, database):
    try:
        conn = await asyncpg.connect(user=user, database=database)
    except asyncpg.InvalidCatalogNameError:
        # Database does not exist, create it.
        conn = await asyncpg.connect(
            database='cafe',
            user='postgres'
        )
        await conn.execute(
            f'CREATE DATABASE "{database}" OWNER "{user}"'
        )
        await conn.close()

        # Connect to the newly created database.
        conn = await asyncpg.connect(user=user, database=database)

        await conn.execute('
            CREATE TABLE cafe(
                id serial PRIMARY KEY,
                name text,
                latitude float8, 
                longitude float8
            );
            INSERT INTO cafe(name, latitude, longitude) 
            VALUES
            ('Coffe Bean', '53.196146', '50.109861'),
            ('Surf Coffe', '53.188422', '50.098061'),
            ('Coffe jungle', '53.199646', '50.112011'),
            ('CoffeCake', '53.209103', '50.118448'),
            ('Puri', '53.196267', '50.124306'),
            ('Carrie', '53.202688', '50.141230')
        ')
        await conn.close()

    return conn


@routes.get('/')
async def index(request):
    return web.Response(
        text='''<html>
        <head>
        <script>
            var socket = new WebSocket('ws://' + window.location.host + '/ws');
            socket.onopen = function() {
                console.log('open');
            };
            socket.onmessage = function(event) {
                let div = document.createElement('div');
                div.className = "message";
                div.innerHTML = "Открылась новая кофейня " + event.data;

                document.body.prepend(div);
                setTimeout(() => div.remove(), 6000);
            };
            socket.onclose = function(event) {
                console.log('close');
                socket.close();
            };
        </script>
        </head>
        <body>
                <h1>Кофе</h1>
                <a href="/set_cafe/">Добавить кофе</a>
                <a href="/get_cafe/">Найти кофе</a>
            </body></html>''',
        content_type="text/html")


@routes.get('/get_cafe/')
async def get_cafe(request):
    if request.rel_url.query:
        row = ''
        latitude = request.rel_url.query['lat']
        longitude = request.rel_url.query['long']
        row = await search_cafe(row, float(latitude), float(longitude))
        return web.Response(text=row)
    
    return web.Response(
        text='''<html><body>
            <form action="/get_cafe/" method="get" accept-charset="utf-8"
                  enctype="multipart/form-data">

                <h2>Ближайшие кофейни Пердоуральска</h2>
                <p>Например 53.195538 50.101783 (центр Самары)</p>
                <h2>Широта</h2>
                <input id="latitude" name="lat" type="text" value="" />
                <h2>Долгота</h2>
                <input id="longitude" name="long" type="text" value="" />

                <input type="submit" value="Найти кофейни" />
            </form>
            </body></html>''',
        content_type="text/html")


@routes.get('/get_cafe/{lat}/{long}/')
async def get_cafe_lat_long(request):
    row = ''
    latitude = request.match_info['lat']
    longitude = request.match_info['long']
    row = await search_cafe(row, float(latitude), float(longitude))
    return web.Response(text=row)


@routes.get('/set_cafe/')
async def set_cafe(request):
    return web.Response(
        text='''<html><body>
            <form action="/post_cafe/" method="post" accept-charset="utf-8"
                  enctype="multipart/form-data">

                <h2>Название кофейни</h2>
                <input id="name" name="name" type="text" value="" />
                <h2>Широта</h2>
                <input id="latitude" name="latitude" type="text" value="" />
                <h2>Долгота</h2>
                <input id="longitude" name="longitude" type="text" value="" />

                <input type="submit" value="Сохранить" />
            </form>
            </body></html>''',
        content_type="text/html")
    

@routes.post('/post_cafe/')
async def post_cafe(request):
    data = await request.post()
    try:
        await save_cafe(request, str(data['name']), int(data['latitude']), int(data['longitude']))
        return web.Response(text='Кафе открыто')
    except ValueError: 
        return web.Response(text='Вы ввели не число')
    print (data['name'], data['latitude'], data['longitude'])

async def search_cafe(row, latitude, longitude):
    row = await app['db'].fetch('''
        SELECT * FROM (SELECT с.*,( 6371 * acos( cos( radians($1) ) * cos( radians( с.latitude ) ) * cos( radians( с.longitude ) - radians($2) ) + sin( radians($1) ) * sin( radians( с.latitude ) ) ) ) < 1 AS distance FROM cafe с ) 
        as distance
        WHERE distance = true
        ''', latitude, longitude)

    if not row:
        row = 'Кофейни по близости не найдены'
    row=str(row)
    return row

async def save_cafe(request, name, latitude, longitude):
    print (name, latitude, longitude)
    await app['db'].execute('''
    INSERT INTO cafe (name, latitude, longitude) VALUES ($1, $2, $3);
    ''', name, latitude, longitude)

    for ws in request.app['websockets']:
        await ws.send_str(name)

async def on_start(app):
    app['db'] = await asyncpg.create_pool('postgresql://postgres:123@localhost:5432/cafe')
    app['websockets'] = []
    print('ok')

async def on_shutdown(app):
    await app['db'].close()
    for ws in app['websockets']:
        await ws.close()
    app['websockets'].clear()


@routes.get('/ws')
async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    request.app['websockets'].append(ws)

    async for msg in ws:
        if msg.type == web.WSMsgType.text:
            await ws.send_str("Hello, {}".format(msg.data))
            print(msg.data)
        elif msg.type == web.WSMsgType.binary:
            await ws.send_bytes(msg.data)
        elif msg.type == web.WSMsgType.close:
            break

    return ws


app = web.Application()
app.on_startup.append(on_start)
app.on_cleanup.append(on_shutdown)
app.add_routes(routes)
web.run_app(app, host='localhost', port=5016)
