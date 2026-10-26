/**
 * Onde fica cada cidade do exterior em que brasileiros votam, para o mapa do
 * mundo da aba Eleições.
 *
 * O TSE publica os locais de votação do exterior sem coordenada (latitude e
 * longitude -1 em todos os 5.430 do arquivo de 2026) e, no lugar do bairro,
 * às vezes o país, às vezes "CENTRO". A tabela abaixo dá o centro aproximado
 * de cada cidade, pelo código do município no TSE (o mesmo das partes
 * `zz-<código>` do feed do exterior): basta para o ponto cair no lugar certo
 * de um mapa do mundo. As 186 cidades são as de 2026; cidade de outro ano que
 * não esteja aqui aparece só na lista abaixo do mapa.
 *
 * Valores: [longitude, latitude], em graus.
 */
export const CIDADES_EXTERIOR: Readonly<Record<string, readonly [number, number]>> = {
  "29254": [-4.03, 5.36], // Abidjã
  "29262": [54.37, 24.45], // Abu Dhabi
  "99198": [7.49, 9.06], // Abuja
  "29270": [-0.19, 5.6], // Accra
  "99325": [38.75, 9.03], // Adis Abeba
  "30457": [4.9, 52.37], // Amsterdã
  "29289": [35.93, 31.95], // Amã
  "29297": [32.86, 39.93], // Ancara
  "29300": [3.06, 36.75], // Argel
  "29319": [-56.47, -30.4], // Artigas
  "29327": [-57.58, -25.26], // Assunção
  "39241": [71.45, 51.17], // Astana
  "29335": [23.73, 37.98], // Atenas
  "39080": [-84.39, 33.75], // Atlanta
  "99171": [44.36, 33.31], // Bagdá
  "39128": [49.87, 40.41], // Baku
  "99350": [-8.0, 12.64], // Bamako
  "29343": [100.5, 13.76], // Bangkok
  "29351": [2.17, 41.39], // Barcelona
  "99473": [50.59, 26.23], // Barein (Manama)
  "29360": [35.5, 33.89], // Beirute
  "29378": [20.46, 44.79], // Belgrado
  "38881": [-88.77, 17.25], // Belmopan
  "29386": [13.4, 52.52], // Berlim
  "29394": [-15.6, 11.86], // Bissau
  "29408": [-74.07, 4.71], // Bogotá
  "29416": [-71.06, 42.36], // Boston
  "39209": [17.11, 48.15], // Bratislava
  "39187": [15.28, -4.27], // Brazzaville
  "29424": [-59.62, 13.1], // Bridgetown
  "29432": [4.35, 50.85], // Bruxelas
  "29440": [26.1, 44.43], // Bucareste
  "29459": [19.04, 47.5], // Budapeste
  "29467": [-58.38, -34.6], // Buenos Aires
  "29475": [-52.33, 4.94], // Caiena
  "29483": [31.24, 30.04], // Cairo
  "29491": [149.13, -35.28], // Camberra
  "30651": [113.26, 23.13], // Cantão
  "29505": [-66.9, 10.48], // Caracas
  "99384": [-60.99, 14.01], // Castries
  "29513": [-87.63, 41.88], // Chicago
  "29521": [-53.46, -33.7], // Chuy
  "29530": [18.42, -33.92], // Cidade do Cabo
  "29556": [-54.61, -25.51], // Ciudad del Este
  "29564": [-62.65, 8.35], // Ciudad Guayana
  "99210": [-68.77, -11.03], // Cobija
  "29572": [-66.16, -17.39], // Cochabamba
  "30929": [79.86, 6.93], // Colombo
  "38903": [-13.68, 9.64], // Conacri
  "29580": [-57.43, -23.41], // Concepción
  "29599": [12.57, 55.68], // Copenhague
  "38920": [2.42, 6.37], // Cotonou
  "29602": [-64.18, -31.42], // Córdoba
  "29610": [-17.45, 14.69], // Dacar
  "29629": [90.41, 23.81], // Dacca
  "29637": [36.29, 33.51], // Damasco
  "38962": [39.28, -6.79], // Dar es Salaam
  "29653": [51.53, 25.29], // Doha
  "29661": [-6.26, 53.35], // Dublin
  "29645": [125.57, -8.56], // Díli
  "99503": [-3.19, 55.95], // Edimburgo
  "29670": [-55.87, -27.33], // Encarnación
  "29688": [18.07, 59.33], // Estocolmo
  "30961": [-7.93, 37.02], // Faro
  "29696": [8.68, 50.11], // Frankfurt
  "30669": [25.91, -24.65], // Gaborone
  "29700": [6.14, 46.2], // Genebra
  "29718": [-58.16, 6.8], // Georgetown
  "98000": [-90.51, 14.63], // Guatemala
  "29742": [137.73, 34.71], // Hamamatsu
  "29750": [105.83, 21.03], // Hanói
  "29769": [31.05, -17.83], // Harare
  "30902": [-72.68, 41.76], // Hartford
  "29777": [-82.37, 23.11], // Havana
  "29785": [24.94, 60.17], // Helsinque
  "29793": [114.17, 22.32], // Hong Kong
  "29807": [-95.37, 29.76], // Houston
  "29815": [11.5, 3.87], // Iaundé
  "38989": [44.51, 40.18], // Ierevan
  "29823": [-73.25, -3.75], // Iquitos
  "29831": [73.05, 33.68], // Islamabade
  "39306": [28.98, 41.01], // Istambul
  "29840": [106.85, -6.21], // Jacarta
  "29173": [85.32, 27.72], // Katmandu
  "29858": [30.52, 50.45], // Kiev
  "99430": [-76.79, 18.02], // Kingston
  "29874": [15.27, -4.44], // Kinshasa
  "29882": [47.98, 29.38], // Kuaite
  "29890": [101.69, 3.14], // Kuala Lumpur
  "29904": [-68.15, -16.5], // La Paz
  "29912": [3.39, 6.52], // Lagos
  "29939": [9.45, 0.39], // Libreville
  "99341": [33.79, -13.96], // Lilongue
  "29947": [-77.04, -12.05], // Lima
  "29955": [-9.14, 38.72], // Lisboa
  "39160": [14.51, 46.06], // Liubliana
  "29963": [1.22, 6.13], // Lomé
  "29971": [-0.13, 51.51], // Londres
  "29980": [-118.24, 34.05], // Los Angeles
  "29998": [13.23, -8.84], // Luanda
  "99287": [28.32, -15.39], // Lusaca
  "30066": [-3.7, 40.42], // Madri
  "39263": [8.78, 3.75], // Malabo
  "30082": [120.98, 14.6], // Manila
  "30074": [-86.25, 12.13], // Manágua
  "30090": [32.57, -25.97], // Maputo
  "99511": [5.37, 43.3], // Marselha
  "39102": [58.41, 23.59], // Mascate
  "39004": [-68.83, -32.89], // Mendoza
  "30104": [-99.13, 19.43], // Cidade do México
  "30112": [-80.19, 25.76], // Miami
  "30120": [9.19, 45.46], // Milão
  "30147": [-56.16, -34.9], // Montevidéu
  "30155": [-73.57, 45.5], // Montreal
  "30163": [37.62, 55.76], // Moscou
  "30171": [72.88, 19.08], // Mumbai
  "30180": [11.58, 48.14], // Munique
  "30198": [136.91, 35.18], // Nagóia
  "30201": [36.82, -1.29], // Nairóbi
  "99180": [-77.35, 25.05], // Nassau
  "39322": [33.38, 35.19], // Nicósia
  "30210": [77.21, 28.61], // Nova Délhi
  "30228": [-74.01, 40.71], // Nova York
  "99490": [-81.38, 28.54], // Orlando
  "30244": [10.75, 59.91], // Oslo
  "30252": [-75.7, 45.42], // Ottawa
  "30260": [-79.52, 8.98], // Cidade do Panamá
  "30279": [-55.2, 5.85], // Paramaribo
  "30287": [2.35, 48.86], // Paris
  "30295": [-57.09, -29.71], // Paso de los Libres
  "30309": [-55.73, -22.55], // Pedro Juan Caballero
  "30317": [116.41, 39.9], // Pequim
  "30325": [-61.52, 10.65], // Port of Spain
  "30341": [-8.61, 41.15], // Porto
  "30333": [-72.34, 18.54], // Porto Príncipe
  "30350": [14.44, 50.08], // Praga
  "30368": [-23.51, 14.93], // Praia
  "30376": [28.19, -25.75], // Pretória
  "99155": [-54.58, -25.6], // Puerto Iguazú
  "99236": [-57.77, -17.78], // Puerto Quijarro
  "99295": [125.76, 39.04], // Pyongyang
  "30392": [-78.47, -0.18], // Quito
  "30406": [-6.84, 34.02], // Rabat
  "30414": [35.2, 31.9], // Ramallah
  "30422": [46.68, 24.71], // Riade
  "30430": [-53.38, -32.6], // Rio Branco (Uruguai)
  "99244": [-55.55, -30.9], // Rivera
  "30449": [12.5, 41.9], // Roma
  "99147": [-61.85, 17.12], // Saint John's
  "30465": [-54.3, -24.06], // Salto del Guairá
  "30473": [-63.18, -17.78], // Santa Cruz de la Sierra
  "99279": [-61.11, 4.6], // Santa Elena de Uairén
  "30481": [-70.67, -33.45], // Santiago
  "30988": [18.41, 43.86], // Sarajevo
  "30538": [126.98, 37.57], // Seul
  "29548": [103.82, 1.35], // Singapura
  "99333": [-51.8, 3.89], // Saint-Georges de l'Oyapock
  "30562": [151.21, -33.87], // Sydney
  "30490": [-69.93, 18.49], // São Domingos
  "30503": [-122.42, 37.77], // São Francisco
  "30511": [-84.09, 9.93], // São José (Costa Rica)
  "30520": [-89.19, 13.69], // São Salvador
  "39225": [6.73, 0.34], // São Tomé
  "30546": [23.32, 42.7], // Sófia
  "30570": [121.56, 25.03], // Taipé
  "99317": [24.75, 59.44], // Talin
  "99104": [44.79, 41.72], // Tbilisi
  "30597": [51.39, 35.69], // Teerã
  "30600": [-87.21, 14.07], // Tegucigalpa
  "30619": [34.78, 32.09], // Tel Aviv
  "99139": [19.82, 41.33], // Tirana
  "30635": [-79.38, 43.65], // Toronto
  "30686": [13.19, 32.89], // Trípoli
  "30708": [10.18, 36.81], // Túnis
  "30627": [139.69, 35.69], // Tóquio
  "39284": [-1.52, 12.37], // Uagadugu
  "39063": [-123.12, 49.28], // Vancouver
  "30740": [21.01, 52.23], // Varsóvia
  "30767": [16.37, 48.21], // Viena
  "30783": [-77.04, 38.91], // Washington
  "30805": [174.78, -41.29], // Wellington
  "30821": [17.08, -22.56], // Windhoek
  "30848": [121.47, 31.23], // Xangai
  "99376": [96.2, 16.87], // Yangon
  "39020": [15.98, 45.81], // Zagreb
  "30864": [8.54, 47.38], // Zurique
};

/** Coordenada da cidade de uma parte do feed do exterior (`zz-<código>`), se a tabela tem. */
export function coordenadaDaCidade(codigoParte: string): readonly [number, number] | null {
  const m = /^zz-(\d+)$/.exec(codigoParte);
  return m ? (CIDADES_EXTERIOR[m[1]!] ?? null) : null;
}

/** Recortes do mapa do mundo, em [oeste, sul, leste, norte] (graus), para os botões de aproximar. */
export const REGIOES_DO_MUNDO: { id: string; rotulo: string; caixa: readonly [number, number, number, number] }[] = [
  { id: "mundo", rotulo: "Mundo", caixa: [-170, -56, 180, 75] },
  { id: "americas", rotulo: "Américas", caixa: [-128, -40, -30, 52] },
  { id: "europa", rotulo: "Europa", caixa: [-12, 34, 40, 62] },
  { id: "africa", rotulo: "África e Oriente Médio", caixa: [-20, -36, 62, 38] },
  { id: "asia", rotulo: "Ásia e Oceania", caixa: [60, -45, 180, 55] },
];
