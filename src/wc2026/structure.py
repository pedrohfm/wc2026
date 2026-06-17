"""Tournament structure: fixtures, knockout bracket, confederations, hosts.
Single source of truth; verbatim from the original monolith.
"""

GROUP_FIXTURES = {
 1:("Mexico","South Africa","A"),2:("South Korea","Czechia","A"),
 3:("Canada","Bosnia & Herzegovina","B"),4:("United States","Paraguay","D"),
 5:("Qatar","Switzerland","B"),6:("Brazil","Morocco","C"),7:("Haiti","Scotland","C"),
 8:("Australia","Türkiye","D"),9:("Germany","Curaçao","E"),10:("Netherlands","Japan","F"),
 11:("Côte d'Ivoire","Ecuador","E"),12:("Sweden","Tunisia","F"),13:("Spain","Cabo Verde","H"),
 14:("Belgium","Egypt","G"),15:("Saudi Arabia","Uruguay","H"),16:("Iran","New Zealand","G"),
 17:("France","Senegal","I"),18:("Iraq","Norway","I"),19:("Argentina","Algeria","J"),
 20:("Austria","Jordan","J"),21:("Portugal","DR Congo","K"),22:("England","Croatia","L"),
 23:("Ghana","Panama","L"),24:("Uzbekistan","Colombia","K"),25:("Czechia","South Africa","A"),
 26:("Switzerland","Bosnia & Herzegovina","B"),27:("Canada","Qatar","B"),28:("Mexico","South Korea","A"),
 29:("United States","Australia","D"),30:("Scotland","Morocco","C"),31:("Brazil","Haiti","C"),
 32:("Türkiye","Paraguay","D"),33:("Netherlands","Sweden","F"),34:("Germany","Côte d'Ivoire","E"),
 35:("Ecuador","Curaçao","E"),36:("Tunisia","Japan","F"),37:("Spain","Saudi Arabia","H"),
 38:("Belgium","Iran","G"),39:("Uruguay","Cabo Verde","H"),40:("New Zealand","Egypt","G"),
 41:("Argentina","Austria","J"),42:("France","Iraq","I"),43:("Norway","Senegal","I"),
 44:("Jordan","Algeria","J"),45:("Portugal","Uzbekistan","K"),46:("England","Ghana","L"),
 47:("Panama","Croatia","L"),48:("Colombia","DR Congo","K"),49:("Switzerland","Canada","B"),
 50:("Bosnia & Herzegovina","Qatar","B"),51:("Scotland","Brazil","C"),52:("Morocco","Haiti","C"),
 53:("Czechia","Mexico","A"),54:("South Africa","South Korea","A"),55:("Ecuador","Germany","E"),
 56:("Curaçao","Côte d'Ivoire","E"),57:("Japan","Sweden","F"),58:("Tunisia","Netherlands","F"),
 59:("Türkiye","United States","D"),60:("Paraguay","Australia","D"),61:("Norway","France","I"),
 62:("Senegal","Iraq","I"),63:("Cabo Verde","Saudi Arabia","H"),64:("Uruguay","Spain","H"),
 65:("Egypt","Iran","G"),66:("New Zealand","Belgium","G"),67:("Panama","England","L"),
 68:("Croatia","Ghana","L"),69:("Colombia","Portugal","K"),70:("DR Congo","Uzbekistan","K"),
 71:("Algeria","Austria","J"),72:("Jordan","Argentina","J"),
}

KO = {
 73:("R32",("RU","A"),("RU","B")), 74:("R32",("W","E"),("3",74)),
 75:("R32",("W","F"),("RU","C")),  76:("R32",("W","C"),("RU","F")),
 77:("R32",("W","I"),("3",77)),    78:("R32",("RU","E"),("RU","I")),
 79:("R32",("W","A"),("3",79)),    80:("R32",("W","L"),("3",80)),
 81:("R32",("W","D"),("3",81)),    82:("R32",("W","G"),("3",82)),
 83:("R32",("RU","K"),("RU","L")), 84:("R32",("W","H"),("RU","J")),
 85:("R32",("W","B"),("3",85)),    86:("R32",("W","J"),("RU","H")),
 87:("R32",("W","K"),("3",87)),    88:("R32",("RU","D"),("RU","G")),
 89:("R16",("WIN",74),("WIN",77)), 90:("R16",("WIN",73),("WIN",75)),
 91:("R16",("WIN",76),("WIN",78)), 92:("R16",("WIN",79),("WIN",80)),
 93:("R16",("WIN",83),("WIN",84)), 94:("R16",("WIN",81),("WIN",82)),
 95:("R16",("WIN",86),("WIN",88)), 96:("R16",("WIN",85),("WIN",87)),
 97:("QF",("WIN",89),("WIN",90)),  98:("QF",("WIN",93),("WIN",94)),
 99:("QF",("WIN",91),("WIN",92)),  100:("QF",("WIN",95),("WIN",96)),
 101:("SF",("WIN",97),("WIN",98)), 102:("SF",("WIN",99),("WIN",100)),
 103:("3rd",("LOSE",101),("LOSE",102)), 104:("Final",("WIN",101),("WIN",102)),
}

THIRD_SLOTS = {74:set("ABCDF"),77:set("CDFGH"),79:set("CEFHI"),80:set("EHIJK"),
               81:set("BEFIJ"),82:set("AEHIJ"),85:set("EFGIJ"),87:set("DEIJL")}

HOSTS = frozenset({"Mexico","Canada","United States"})

# Confederation of each team (static; used for the inter-confed noise shock)
CONF = {
 "Mexico":"CONCACAF","Canada":"CONCACAF","United States":"CONCACAF",
 "Haiti":"CONCACAF","Curaçao":"CONCACAF","Panama":"CONCACAF",
 "Brazil":"CONMEBOL","Paraguay":"CONMEBOL","Ecuador":"CONMEBOL",
 "Uruguay":"CONMEBOL","Colombia":"CONMEBOL","Argentina":"CONMEBOL",
 "South Korea":"AFC","Qatar":"AFC","Australia":"AFC","Japan":"AFC","Iran":"AFC",
 "Saudi Arabia":"AFC","Iraq":"AFC","Jordan":"AFC","Uzbekistan":"AFC",
 "South Africa":"CAF","Morocco":"CAF","Côte d'Ivoire":"CAF","Tunisia":"CAF",
 "Egypt":"CAF","Cabo Verde":"CAF","Senegal":"CAF","Algeria":"CAF",
 "DR Congo":"CAF","Ghana":"CAF",
 "Czechia":"UEFA","Switzerland":"UEFA","Bosnia & Herzegovina":"UEFA","Türkiye":"UEFA",
 "Germany":"UEFA","Netherlands":"UEFA","Sweden":"UEFA","Belgium":"UEFA","Spain":"UEFA",
 "France":"UEFA","Norway":"UEFA","Austria":"UEFA","Portugal":"UEFA","England":"UEFA",
 "Croatia":"UEFA","Scotland":"UEFA","New Zealand":"OFC",
}

_GROUP_OF = {t: g for (t1, t2, g) in GROUP_FIXTURES.values() for t in (t1, t2)}


def _teams_in_group(g):
    seen = []
    for t1, t2, gg in GROUP_FIXTURES.values():
        if gg == g:
            for t in (t1, t2):
                if t not in seen: seen.append(t)
    return seen


GROUPS = {g: _teams_in_group(g) for g in sorted(set(_GROUP_OF.values()))}

# Knockout match-number ranges by round (used by the Monte Carlo tally)
R32, R16, QFM, SFM = range(73, 89), range(89, 97), range(97, 101), (101, 102)
