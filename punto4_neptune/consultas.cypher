// name: q1_recomendar_amigos
// pregunta: ¿A quién podría conocer Ana? Amigos de sus amigos que aún no conoce (2 saltos por CONOCE).
MATCH (a:Estudiante {nombre: 'Ana'})-[:CONOCE]-(amigo:Estudiante)-[:CONOCE]-(sugerido:Estudiante)
WHERE sugerido <> a
OPTIONAL MATCH (a)-[ya:CONOCE]-(sugerido)
WITH sugerido, amigo, ya
WHERE ya IS NULL
RETURN sugerido.nombre AS sugerido, collect(DISTINCT amigo.nombre) AS amigos_en_comun,
       count(DISTINCT amigo) AS num_amigos_comun
ORDER BY num_amigos_comun DESC, sugerido;

// name: q2_profesores_de_medellin
// pregunta: ¿Qué profesores dictan cursos a estudiantes que viven en Medellín, en qué cursos y a quiénes? (3 saltos: Ciudad<-VIVE_EN-Estudiante-INSCRITO_EN->Curso<-DICTA-Profesor)
MATCH (ciudad:Ciudad {nombre: 'Medellín'})<-[:VIVE_EN]-(e:Estudiante)-[i:INSCRITO_EN]->(c:Curso)<-[:DICTA]-(p:Profesor)
RETURN p.nombre AS profesor, c.nombre AS curso, collect(e.nombre) AS estudiantes,
       avg(i.nota) AS nota_promedio
ORDER BY profesor, curso;

// name: q3_ruta_prerrequisitos
// pregunta: ¿Qué cursos hay que aprobar antes de Visión Artificial? (camino de longitud variable por REQUIERE)
MATCH ruta = (c:Curso {nombre: 'Visión Artificial'})-[:REQUIERE*1..5]->(pre:Curso)
RETURN pre.nombre AS prerrequisito, length(ruta) AS nivel
ORDER BY nivel;

// name: q4_cadena_contactos
// pregunta: ¿Por qué cadena de conocidos llega Ana hasta Felipe? (caminos de hasta 4 saltos por CONOCE)
MATCH ruta = (a:Estudiante {nombre: 'Ana'})-[:CONOCE*1..4]-(f:Estudiante {nombre: 'Felipe'})
RETURN nodes(ruta) AS nodos, length(ruta) AS saltos
ORDER BY saltos
LIMIT 3;
