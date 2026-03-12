document.addEventListener("DOMContentLoaded", () => {
  const firstInput = document.querySelector("#movie");
  if (firstInput) {
    firstInput.focus();
  }

  const cards = document.querySelectorAll(".recommend-list li");
  cards.forEach((card, index) => {
    card.style.animationDelay = `${index * 70}ms`;
  });
});
