def load_regions(path, session):
    gdf = gpd.read_file(path)
    for _, row in gdf.iterrows():
        session.add(Region(
            name=row["adm1_name"],      # English — confirmed correct
            name_fr=row["adm1_name1"],  # French
            pcode=row["adm1_pcode"],
            geom=from_shape(row.geometry, srid=4326),
        ))

def load_departments(path, session):
    gdf = gpd.read_file(path)
    for _, row in gdf.iterrows():
        region = session.query(Region).filter_by(pcode=row["adm1_pcode"]).first()
        session.add(Department(
            name=row["adm2_name1"],     # corrected — adm2_name is empty
            pcode=row["adm2_pcode"],
            region_id=region.id if region else None,
            geom=from_shape(row.geometry, srid=4326),
        ))

def load_arrondissements(path, session):
    gdf = gpd.read_file(path)
    for _, row in gdf.iterrows():
        dept = session.query(Department).filter_by(pcode=row["adm2_pcode"]).first()
        session.add(Arrondissement(
            name=row["adm3_name1"],     # corrected — adm3_name is empty
            pcode=row["adm3_pcode"],
            department_id=dept.id if dept else None,
            geom=from_shape(row.geometry, srid=4326),
        ))