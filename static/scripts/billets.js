document.getElementById('epreuve-select').addEventListener('change', function() {
  const selectedEpreuve = this.value;
  console.log('Épreuve sélectionnée :', selectedEpreuve);  // Vérifie la sélection dans la console
  if (selectedEpreuve) {
    const targetElement = document.querySelector(selectedEpreuve);
    if (targetElement) {
      const offset = targetElement.getBoundingClientRect().top + window.scrollY - (window.innerHeight / 2) + (targetElement.clientHeight / 2);
      window.scrollTo({
        top: offset,
        behavior: 'smooth' // Scroll en douceur
      });
    } else {
      console.error('Élément introuvable pour :', selectedEpreuve);
    }
  }
});
